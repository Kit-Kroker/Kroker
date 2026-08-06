"""A trivial target the compose adapter can deploy. VERSION comes from the
image tag, so a rollback is observable from outside: the endpoint reports
which version is serving. HEALTHY=0 makes a version that fails its smoke
check without failing its build."""
import os

from fastapi import FastAPI, Response

app = FastAPI()
VERSION = os.environ.get("APP_VERSION", "unset")
HEALTHY = os.environ.get("HEALTHY", "1") == "1"


@app.get("/health")
def health(response: Response):
    if not HEALTHY:
        response.status_code = 500
    return {"version": VERSION, "healthy": HEALTHY}
