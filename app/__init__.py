import os
import logging, logging.handlers

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

#from sqlalchemy.orm import sessionmaker

import rq
from redis import Redis

db = SQLAlchemy()

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object('config')
    app.config.from_pyfile('config.py', silent=True)

    # setting of logging of app-specific messages to safe.log
    handler = logging.FileHandler('safe.log')
    handler.setLevel(app.config.get('LOGGING_LEVEL', logging.INFO))
    formatter = logging.Formatter('%(asctime)s %(levelname)s [%(filename)s:%(lineno)d - %(funcName)s] : %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    if app.config.get('EMAIL_ERRORS', False):
        # email error and critical events to admin(s)
        mail_handler = logging.handlers.SMTPHandler(mailhost=app.config['SMTP_SERVER'],
                                                    fromaddr=app.config['EMAIL_FROM'],
                                                    toaddrs=app.config['EMAIL_ERRORS_TO'],
                                                    subject="SAFE Error Report")
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

    # ensure that the instance folder exists (creating if necessary)
    os.makedirs(app.instance_path, exist_ok=True)

    from app.database import init_app as init_app_db
    init_app_db(app)

    if app.config.get("MOCK_CAS") == True:
        if app.config.get("CAS_SERVER_URL") is not None:
            app.logger.error("CAS_SERVER_URL must be None when MOCK_CAS is set.")
            return None

        from app import cas
        app.register_blueprint(cas.cas, url_prefix="/cas")
    
    if app.config.get("MOCK_CAS") and app.config.get("CAS_SERVER_URL") is not None:
        app.logger.error("CAS_SERVER_URL must be None when MOCK_CAS is set.")
        return None

    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.test_queue = rq.Queue('safe-tests', connection=app.redis)

    from app import admin
    app.register_blueprint(admin.admin, url_prefix="/admin")

    from app import auth
    app.register_blueprint(auth.auth, url_prefix="/auth")

    from . import notify
    app.register_blueprint(notify.notify, url_prefix="/notify")

    from app import user_views
    app.register_blueprint(user_views.user_views)

    #from app import tests
    #app.register_blueprint(tests.tests, url_prefix="/tests") # FIXME: only in testing mode

    auth.init_auth(app)

    with app.app_context():
        app.logger.debug("CREATING ALL TABLES!")
        db.create_all()

    return app
