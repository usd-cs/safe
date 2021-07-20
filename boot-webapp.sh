#!/bin/sh
source venv/bin/activate

exec flask run -h 0.0.0.0
#exec gunicorn -b :5000 --access-logfile - --error-logfile - safe:app
