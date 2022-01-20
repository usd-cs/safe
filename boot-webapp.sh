#!/bin/bash
source venv/bin/activate

#exec flask run -h 0.0.0.0 --port 6000
export SCRIPT_NAME=/safe
exec gunicorn -b 0.0.0.0:6000 --access-logfile - --error-logfile - safe:app
