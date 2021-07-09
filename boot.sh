#!/bin/sh
source venv/bin/activate

exec flask run
#exec gunicorn -b :5000 --access-logfile - --error-logfile - safe:app
