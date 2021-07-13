import os

from flask import Flask
from sqlalchemy.orm import sessionmaker, joinedload
from flask_login import LoginManager

import rq
from redis import Redis

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
    
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.test_queue = rq.Queue('safe-tests', connection=app.redis)

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

    @app.route("/notify/<course>-<semester>-s<int:section>-psa<int:psa>")
    @app.route("/notify/<course>-<semester>-s<int:section>-psa<int:psa>-group<int:group>")
    def handle_notification(course, semester, section, psa, group=None):
        repo_dir = os.path.join(app.instance_path, 'repositories')

        repo_name = f"{course}-{semester}-s{section:02}-psa{psa}"
        if group:
            repo_name += f"-group{group}"

        test_code_dir = '/Users/sat/Teaching/comp110-ci-server/tester_code/psa1'
        test_command = ['python3', 'my_autograde.py']
        source_files = ['name_drawer.py']

        job = app.test_queue.enqueue('app.workers.run_test', repo_dir,
                                        repo_name, test_code_dir, test_command,
                                        15, source_files)
        print(f"New Job ID: {job.get_id()}")

        while not job.is_finished:
            print("Job not done yet!")
            import time
            time.sleep(2)

        print("Job is done!")
        return "YAYAY!"

        """
        shared_queue.put((section, psa, group))
        place_in_queue = shared_queue.qsize()

        return f"Request received. You are at position {place_in_queue} in the work queue.\n"
        """


    return app
