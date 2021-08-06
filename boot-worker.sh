#!/bin/bash
source venv/bin/activate

exec rq worker safe-tests
