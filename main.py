import os
import subprocess
import uvicorn

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from threading import Lock
from typing_extensions import Annotated


# Hosting config
CONFIG_HOST = os.environ.get('PIP_INSTALLER_HOST', '0.0.0.0')
CONFIG_PORT = os.environ.get('PIP_INSTALLER_PORT', 8000)

# Auth config
CONFIG_AUTH_USERNAME = os.environ['PIP_INSTALLER_USERNAME']
CONFIG_AUTH_PASSWORD = os.environ['PIP_INSTALLER_PASSWORD']

# Command config
CONFIG_PIP_CMD = 'pip3'
CONFIG_REPO_URL = os.environ['PIP_INSTALLER_REPO_URL']
CONFIG_ALLOWED_PACKAGES = os.environ['PIP_INSTALLER_PACKAGES']
SSH_KEY_PATH = os.environ.get('SSH_KEY_PATH', None)


# Validation config
ALLOWED_PACKAGES_ARRAY = CONFIG_ALLOWED_PACKAGES.split(',')
PACKAGE_REGEXP = f'^{"|".join(ALLOWED_PACKAGES_ARRAY)}$' # Working around inability to generate a Literal array dynamically as of yet


app = FastAPI()
security = HTTPBasic()
lock = Lock()


def authenticate(credentials):
 if not(credentials.username == CONFIG_AUTH_USERNAME and credentials.password == CONFIG_AUTH_PASSWORD):
   raise HTTPException(status_code=401)

def execute_within_lock(lock, predicate, parameters):
 if not(lock.acquire(blocking=False)):
   raise HTTPException(status_code=503)
 try:
   result = predicate(parameters)
 finally:
   lock.release()
 return result

def pip_install_env_varialbes():
  if SSH_KEY_PATH is not None:
    return {'GIT_SSH_COMMAND': f'ssh -i {SSH_KEY_PATH}'}
  return None

def run(args):
  process = subprocess.run(args, capture_output=True, text=True, env=pip_install_env_varialbes())
  return [process.returncode, process.stdout, process.stderr]
   
def install_critical_section(parameters):
  return run([CONFIG_PIP_CMD, 'install', f'git+ssh://{CONFIG_REPO_URL}/{parameters.package}.git'])

def show_critical_section(parameters):
  return run([CONFIG_PIP_CMD, 'show', parameters.package])

def make_payload(run_result):
  return { 'return_code': run_result[0], 'std_out': run_result[1], 'std_err': run_result[2] }

class Parameters(BaseModel):
  package: Annotated[str, Query(pattern=PACKAGE_REGEXP)]

@app.post('/show')
def get(credentials: Annotated[HTTPBasicCredentials, Depends(security)], parameters: Parameters):
  authenticate(credentials)
  output = execute_within_lock(lock, show_critical_section, parameters)
  return make_payload(output)
  
@app.post('/install')
def install(credentials: Annotated[HTTPBasicCredentials, Depends(security)], parameters: Parameters):
  authenticate(credentials)
  output = execute_within_lock(lock, install_critical_section, parameters)
  return make_payload(output)


if __name__ == "__main__":
    uvicorn.run('main:app', host=CONFIG_HOST, port=CONFIG_PORT)
