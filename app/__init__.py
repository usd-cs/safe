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

    @app.route("/notify/failed/<job_id>", methods=["post"])
    def remove_failed(job_id):
        from flask import request

        failure_info = request.get_json()
        if failure_info:
            print("Failure Reason:", failure_info["error"])
        else:
            return "Failure info expected in JSON format"

        with app.Session() as session:
            test_results = (
                session.query(db_models.TestResults)
                    .filter(db_models.TestResults.job_id == job_id)
                    .first()
            )

            if not test_results:
                abort(404)
            else:
                # remove the test results
                session.delete(test_results)
                session.commit()
                return "Failure notification received."


    @app.route("/notify/success/<job_id>", methods=["post"])
    def update_results(job_id):
        from rq.job import Job
        from flask import request
        import json
        from dateutil import parser

        results_data = request.get_json()
        if not results_data:
            return "Test results expected in JSON format"

        with app.Session() as session:
            test_results = (
                session.query(db_models.TestResults)
                    .filter(db_models.TestResults.job_id == job_id)
                    .first()
            )

            if not test_results:
                abort(404)

            job = Job.fetch(job_id, connection=app.redis)

            # TODO: if job.is_finished isn't true, log and return

            test_results.finished = True
            test_results.results = json.dumps(results_data['results'])
            test_results.commit_time = parser.parse(results_data['submission_time'])
            test_results.commit_comment = results_data['commit_comment']
            test_results.commit_author = results_data['author']
            test_results.completed_at = parser.parse(results_data['results_time'])

            group = test_results.team
            assignment = group.assignment
            section = assignment.section

            repo_name = f"{section.course}-{section.semester}-s{section.section_num:02}-psa{assignment.num}"

            # FIXME: this breaks for non-group based assignments like comp110
            # psa0
            repo_name += f"-group{group.team_num}"

            testing_dir = os.path.join(app.config['REPOSITORY_BASE_DIR'],
                                        repo_name, 'safe_testing', job_id)

            # add student submitted files to test results
            source_files = [sf.filename for sf in test_results.team.assignment.base_assignment.files]
            source_filenames = workers.get_filenames(source_files)

            for filename in source_filenames:
                file_path = os.path.join(testing_dir, filename)

                with open(file_path, 'rb') as source_file:
                    file_contents = source_file.read()
                    
                submitted_file = db_models.SubmittedFile(filename=filename,
                                                            data=file_contents,
                                                            job_id=job_id)

                session.add(submitted_file)

            session.commit()

        return "Results successfully received"

    @app.route("/notify/<course>-<semester>-s<int:section>-psa<int:psa>")
    @app.route("/notify/<course>-<semester>-s<int:section>-psa<int:psa>-group<int:group>")
    def handle_notification(course, semester, section, psa, group=None):

        with app.Session() as session:
            target_group = (
                session.query(db_models.Team)
                    .join(db_models.Section.assignments)
                    .join(db_models.Assignment.teams)
                    .filter(db_models.Section.course == course)
                    .filter(db_models.Section.semester == semester)
                    .filter(db_models.Section.section_num == section)
                    .filter(db_models.Assignment.num == psa)
                    .filter(db_models.Team.team_num == group) # FIXME: only when not None
                    .first()
            )

            if not target_group:
                return "Invalid parameters for notify"

            # TODO: if there are results in progress (i.e. in queue or
            # processing), cancel them and put this in the queue instead

            repo_name = f"{course}-{semester}-s{section:02}-psa{psa}"
            if group:
                repo_name += f"-group{group}"

            base_assignment = target_group.assignment.base_assignment

            test_code_dir = os.path.join(app.config['TESTER_CODE_BASE_DIR'],
                                            f"{base_assignment.assignment_id}")

            # FIXME: if test_code_dir doesn't exist, create it based on
            # TesterFiles associated with the assignment

            test_command = base_assignment.tester_run_command.split()
            source_files = [sf.filename for sf in base_assignment.files]
            tester_files = [tf.filename for tf in base_assignment.tester_files]
            max_runtime = base_assignment.max_runtime

            job = app.test_queue.enqueue('app.workers.run_test',
                                            'code.sandiego.edu',
                                            app.config['REPOSITORY_BASE_DIR'],
                                            repo_name, test_code_dir, test_command,
                                            max_runtime, source_files,
                                            tester_files,
                                            on_success=workers.testing_successful,
                                            on_failure=workers.testing_failed)
            print(f"New Job ID: {job.get_id()}")

            new_test_results = db_models.TestResults(job_id=job.get_id(),
                                                        team_id=target_group.team_id)

            session.add(new_test_results)
            session.commit()


        # TODO: add information about place in queue.
        return "Notifcation successfully received."


    return app
