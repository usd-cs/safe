import os
import logging

SECRET_KEY = 'dev'
DATABASE_URI = 'sqlite:///:memory:'
DATABASE_VERBOSE = False
REDIS_URL = 'redis://'
SERVER_NAME = 'localhost:5000'
APPLICATION_ROOT = '/safe'
CAS_SERVER_URL = None
EMAIL_ENABLED = False
TESTER_CODE_BASE_DIR = os.path.join(os.getcwd(), 'tester_code')
REPOSITORY_BASE_DIR = os.path.join(os.getcwd(), 'repositories')
LOGGING_LEVEL=logging.INFO
