#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -r requirements.txt
printf '\nRADAR: abre http://localhost:8000\nAdmin inicial: data/admin_credentials.txt\n'
python run.py
