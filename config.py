import os
import logging

SECRET_KEY = 'dev'
SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
SQLALCHEMY_TRACK_MODIFICATIONS = False
DATABASE_VERBOSE = False
REDIS_URL = 'redis://'
SERVER_NAME = 'localhost:5000'
APPLICATION_ROOT = '/safe'
CAS_SERVER_URL = None
TESTER_CODE_BASE_DIR = os.path.join(os.getcwd(), 'tester_code')
REPOSITORY_BASE_DIR = os.path.join(os.getcwd(), 'repositories')
LOGGING_LEVEL=logging.INFO
EMAIL_ERRORS = False
