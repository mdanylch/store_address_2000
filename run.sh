#!/bin/sh
# App Runner *start* command: sh run.sh
# Listens on $PORT (App Runner sets PORT; default 8080 for local checks).

set -e
cd "$(dirname "$0")"
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
