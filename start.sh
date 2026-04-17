#!/bin/sh
# App Runner *build* command: sh start.sh
# Installs Python dependencies into the build environment.

set -e
cd "$(dirname "$0")"
python3 --version
pip3 install --no-cache-dir -r requirements.txt
