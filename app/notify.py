import os
import json
from dateutil import parser

from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from rq.job import Job

from . import db_models

notify = Blueprint('notify', __name__)

@notify.route("/failed/<job_id>", methods=["post"])
def remove_failed(job_id):
    failure_info = request.get_json()
    if failure_info:
        current_app.logger.info(f"Failure Reason: {failure_info['error']}")
    else:
        return "Failure info expected in JSON format"

    with current_app.Session() as session:
        test_results = (
            session.query(db_models.TestResults)
                .filter(db_models.TestResults.job_id == job_id)
                .first()
        )

        if not test_results:
            current_app.logger.error(f"Invalid Job ID: {job_id}")
            abort(404)
        else:
            # remove the test results
            session.delete(test_results)
            session.commit()
            current_app.logger.info(f"Removed failed job with ID {job_id}")
            return "Failure notification received."


@notify.route("/success/<job_id>", methods=["post"])
def update_results(job_id):
    from app.workers import get_filenames

    results_data = request.get_json()
    if not results_data:
        current_app.logger.error("Test results not found")
        return "Test results expected in JSON format"

    with current_app.Session() as session:
        test_results = (
            session.query(db_models.TestResults)
                .filter(db_models.TestResults.job_id == job_id)
                .first()
        )

        if not test_results:
            current_app.logger.error(f"Invalid Job ID: {job_id}")
            abort(404)

        job = Job.fetch(job_id, connection=current_app.redis)

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

        repo_dir = os.path.join(current_app.config['REPOSITORY_BASE_DIR'], repo_name)
        testing_dir = os.path.join(repo_dir, 'safe_testing', job_id)

        current_app.logger.debug(f"Getting source files from {testing_dir}")

        # add student submitted files to test results
        source_files = [sf.filename for sf in test_results.team.assignment.base_assignment.files]
        source_filenames = get_filenames(source_files, repo_dir)

        for filename in source_filenames:
            file_path = os.path.join(testing_dir, filename)

            with open(file_path, 'rb') as source_file:
                file_contents = source_file.read()
                
            submitted_file = db_models.SubmittedFile(filename=filename,
                                                        data=file_contents,
                                                        job_id=job_id)

            session.add(submitted_file)
            current_app.logger.debug(f"Saved file {filename}")

        session.commit()

    return "Results successfully received"

@notify.route("<course>-<semester>-s<int:section>-psa<int:psa>")
@notify.route("<course>-<semester>-s<int:section>-psa<int:psa>-group<int:group>", methods=['post'])
def handle_notification(course, semester, section, psa, group=None):
    from app.workers import testing_successful, testing_failed

    with current_app.Session() as session:
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
            current_app.logger.warning(f"No team found for {course}, {semester}, Section {section}, PSA {psa}, Group # {group}")
            return "Invalid parameters for notify", 404

        # TODO: if there are results in progress (i.e. in queue or
        # processing), cancel them and put this in the queue instead

        repo_name = f"{course}-{semester}-s{section:02}-psa{psa}"
        if group:
            repo_name += f"-group{group}"

        base_assignment = target_group.assignment.base_assignment

        test_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                        f"{base_assignment.assignment_id}")

        if not os.path.isdir(test_code_dir):
            # TODO: if test_code_dir doesn't exist, create it based on
            # TesterFiles associated with the assignment
            current_app.logger.critical(f"Missing Test code directory: {test_code_dir}")
            abort(500)

        test_command = base_assignment.tester_run_command.split()
        source_files = [sf.filename for sf in base_assignment.files]
        tester_files = [tf.filename for tf in base_assignment.tester_files]
        max_runtime = base_assignment.max_runtime

        group_members = [member.username for member in target_group.members]

        job = current_app.test_queue.enqueue('app.workers.run_test',
                                        'code.sandiego.edu',
                                        current_app.config['REPOSITORY_BASE_DIR'],
                                        repo_name, test_code_dir, test_command,
                                        max_runtime, source_files,
                                        tester_files, group_members,
                                        on_success=testing_successful,
                                        on_failure=testing_failed)

        current_app.logger.info(f"Enqueued {repo_name}. Job ID: {job.get_id()}")

        new_test_results = db_models.TestResults(job_id=job.get_id(),
                                                    team_id=target_group.team_id)

        session.add(new_test_results)
        session.commit()


    # TODO: add information about place in queue.
    return "Notifcation successfully received."

