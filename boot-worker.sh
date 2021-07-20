#!/bin/sh
source venv/bin/activate

exec rq worker safe-tests
