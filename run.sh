#!/bin/sh
# App Runner *start* command: sh run.sh
#
# Fusion build installs deps in the *build* image; the runtime image only COPYs
# /app, so site-packages from the build are not present. Re-install here, then
# start Uvicorn. Listens on $PORT (App Runner sets it; default 8080).

set -e
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
pip3 install --no-cache-dir -r requirements.txt
exec python3 -m uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
