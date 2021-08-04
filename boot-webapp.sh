#!/bin/sh
source venv/bin/activate

#exec flask run -h 0.0.0.0
export SCRIPT_NAME=/safe
exec gunicorn -b 0.0.0.0:5000 --access-logfile - --error-logfile - safe:app
