#!/bin/sh
# App Runner *build* command: sh start.sh
#
# Install wheels into ./deps so they are COPY'd with /app into the runtime
# image. (Runtime image does not keep site-packages from the build stage.)

set -e
cd "$(dirname "$0")"
python3 --version
rm -rf deps
pip3 install --no-cache-dir -r requirements.txt -t deps
