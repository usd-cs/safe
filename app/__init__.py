import os

from flask import Flask
from sqlalchemy.orm import sessionmaker, joinedload
from flask_login import LoginManager

from . import user_views
from . import admin
from . import auth
from . import db
from . import db_models

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object('config')
    app.config.from_pyfile('config.py', silent=True)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # try to make the instance folder
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db_engine = db.init_db(app)
    app.Session = sessionmaker(db_engine)

    app.register_blueprint(admin.admin, url_prefix="/admin")
    app.register_blueprint(auth.auth, url_prefix="/auth")
    app.register_blueprint(user_views.user_views)


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
