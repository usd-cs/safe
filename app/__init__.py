import os

from flask import Flask, url_for
from sqlalchemy.orm import sessionmaker, joinedload
from flask_login import LoginManager

import rq
from redis import Redis

from cas import CASClient

from . import user_views
from . import admin
from . import auth
from . import notify
from . import db
from . import db_models
from . import workers


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object('config')
    app.config.from_pyfile('config.py', silent=True)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    assert app.config['CAS_SERVER_URL'] is not None, "CAS_SERVER_URL not set in config"

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
    

    with app.app_context():
        app.cas_client = CASClient(
            version=3,
            service_url=f"{url_for('auth.verify_ticket', next=url_for('user_views.root', _external=False))}",
            server_url=app.config['CAS_SERVER_URL']
        )

    #print('CAS service_url:', app.cas_client.service_url)

    @login_manager.user_loader
    def load_user(user_id):
        print("loading user:", user_id)

        with app.Session() as session:
            matching_users = (
                session.query(db_models.User)
                    .options(joinedload(db_models.User.sections))
                    .filter(db_models.User.user_id == int(user_id))
            )

        if matching_users.count() == 1:
            return matching_users.first()
        else:
            print(f"Couldn't find user with id {user_id}")
            return None


    return app
