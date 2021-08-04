import os

from flask import Flask
from sqlalchemy.orm import sessionmaker

import rq
from redis import Redis

from . import user_views
from . import admin
from . import auth
from . import notify
from . import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object('config')
    app.config.from_pyfile('config.py', silent=True)

    # ensure that the instance folder exists (creating if necessary)
    os.makedirs(app.instance_path, exist_ok=True)

    db_engine = db.init_db(app)
    app.Session = sessionmaker(db_engine)
    
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.test_queue = rq.Queue('safe-tests', connection=app.redis)

    app.register_blueprint(admin.admin, url_prefix="/admin")
    app.register_blueprint(auth.auth, url_prefix="/auth")
    app.register_blueprint(notify.notify, url_prefix="/notify")
    app.register_blueprint(user_views.user_views)
    
    auth.init_auth(app)
    db.init_app(app)

    return app
