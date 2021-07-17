import os

SECRET_KEY = 'dev'
DATABASE_URI = 'sqlite:///:memory:'
DATABASE_VERBOSE = False
REDIS_URL = 'redis://'
MAX_PASSWORD_RESET_TIME = 15
SERVER_BASE_URL = 'http://localhost:5000'
EMAIL_ENABLED = False
FIRST_ADMIN_USER = ('admin', 'System', 'Admin')
TESTER_CODE_BASE_DIR = os.path.join(os.getcwd(), 'tester_code')
