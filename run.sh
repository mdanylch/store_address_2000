#!/bin/sh
# App Runner *start* command: sh run.sh
#
# Dependencies live in ./deps (created in build). Start Uvicorn immediately so
# health checks do not time out during a long pip install.

set -e
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$(pwd)/deps:${PYTHONPATH:-}"
exec python3 -m uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
