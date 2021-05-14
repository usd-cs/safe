from flask import Flask, render_template, request, redirect, flash, abort, url_for
from flask_login import LoginManager, current_user, login_user, logout_user, login_required, UserMixin
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField
from wtforms.validators import ValidationError, DataRequired, Length

from multiprocessing import Process, Queue
import os
import subprocess
import sys

import datetime
from sqlalchemy import create_engine, or_, and_
from sqlalchemy.orm import sessionmaker
from db_models import *

app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.config['SECRET_KEY'] = 'change_this_to_a_random_value'

engine = create_engine('sqlite:///raft.db', connect_args={'check_same_thread': False}, echo=False)

course_name = 'cs1'
term_name = 'sp21'

# create a Session
Session = sessionmaker(bind=engine)
db_session = Session()

shared_queue = Queue()

@login_manager.user_loader
def load_user(user_id):
    print("loading user:", user_id)

    matching_students = db_session.query(Student).filter(Student.student_id == int(user_id))
    matching_instructors = db_session.query(Instructor).filter(Instructor.instructor_id == int(user_id))

    if matching_students.count() == 1:
        return matching_students.first()
    elif matching_instructors.count() == 1:
        return matching_instructors.first()
    else:
        print("Couldn't find user with id {user_id}")
        sys.exit(1)

class GetTestResultsForm(FlaskForm):
    username = StringField(label=('RAFT Username:'), validators=[DataRequired()])
    password = PasswordField(label=('RAFT Password:'), validators=[DataRequired()])
    submit = SubmitField(label=('Submit'))

def is_section_instructor(user, section_num):
    """
    Returns true if the given user is listed as the instructor for the
    given section number.
    """
    return db_session.query(Instructor.username).select_from(Section).join(Instructor).filter(and_(Section.section_id ==
        section_num, Instructor.username == user.username)).count() == 1

@app.route("/s<int:section_num>/students/")
@login_required
def list_students(section_num):
    if not is_section_instructor(current_user, section_num):
        abort(403)

    students_in_section = (
            db_session.query(Student)
                .filter(Student.section_id == section_num)
                .all()
            )

    students_str = [f"<br/>{s.username}" for s in students_in_section]
    return "\n".join(students_str)

@app.route("/s<int:section_num>/psa<int:psa_num>/")
@login_required
def list_groups(section_num, psa_num):
    if not is_section_instructor(current_user, section_num):
        abort(403)

    groups_in_psa = (
        db_session.query(Team.team_id, Team.team_num)
            .filter(and_(Team.section_id == section_num, 
                            Team.psa_id == psa_num))
            .all()
    )

    if len(groups_in_psa) == 0:
        return f"No groups found for Section {section_num:02}, PSA {psa_num}"

    result_str = "";

    # TODO: Replace this with a jinja template
    for team_id, team_num in groups_in_psa:

        result_str += f"<br/><b>Group{team_num:02}:</b>\n"
        result_str += f"<br/>- <a href='{url_for('psa_results', section_num=section_num, psa_num=psa_num, group_num=team_num)}'>Results</a></b>\n"
        result_str += f"<br/>- Students: "

        students_in_group = (
            db_session.query(Student)
                .join(student_team)
                .join(Team)
                .filter(Team.team_id == team_id)
                .all()
        )

        students_str = [f"{s.username}" for s in students_in_group]
        result_str += ", ".join(students_str)
        result_str += "\n"

    return result_str


@app.route("/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
@login_required
def psa_results(section_num, psa_num, group_num):
    if not is_section_instructor(current_user, section_num):
        abort(403)

    q = db_session.query(Team).filter(and_(Team.team_num == group_num,
        Team.psa_id == psa_num, Team.section_id == section_num))

    if q.count() != 1:
        abort(404)

    repo_name = f'{course_name}-{term_name}-s{section_num:02}-psa{psa_num}-group{group_num}'

    if not os.path.isfile(f"/var/repos/{repo_name}/tester/results.html"):
        return "Could not locate test results. Please contact your instructor."

    with open(f"/var/repos/{repo_name}/tester/results.html", 'r') as results_file:
        return results_file.read()


@app.route("/dashboard/")
@login_required
def instructor_dashboard():
    if db_session.query(Instructor).filter(current_user.username == Instructor.username).count() == 1:
        all_sections = (
                db_session.query(Section.section_id)
                    .filter(Section.instructor_id == current_user.instructor_id)
                    .all()
                )
        for s in all_sections:
            print(s.section_id)

        all_students = (
                db_session.query(Student.username)
                    .select_from(Section)
                    .join(Student)
                    .filter(Section.instructor_id == current_user.instructor_id)
                    .all()
                )
        print(all_students)
        return "You are an instructor!"
    else:
        abort(403)


@app.route(f"/notify/{course_name}-{term_name}-s<int:section>-psa<int:psa>")
@app.route(f"/notify/{course_name}-{term_name}-s<int:section>-psa<int:psa>-group<int:group>")
def handle_notification(section, psa, group=None):
    shared_queue.put((section, psa, group))
    place_in_queue = shared_queue.qsize()

    return f"Request received. You are at position {place_in_queue} in the work queue.\n"


@app.route('/login/', methods = ['POST', 'GET'])
def login():
    if current_user.is_authenticated:
        next_url = request.args.get('next')
        if next_url is None:
            return f"You are currently logged in as <b>{current_user.username}</b>."
        else:
            print(next_url)
            return redirect(next_url)

    error = None
    form = GetTestResultsForm()
    if form.validate_on_submit():
        instructor_matches = (
            db_session.query(Instructor)
                .filter(Instructor.username == form.username.data)
        )

        student_matches = (
            db_session.query(Student)
                .filter(Student.username == form.username.data)
        )

        matching_user = None
        if instructor_matches.count() == 1:
            matching_user = instructor_matches.first()
        elif student_matches.count() == 1:
            matching_user = student_matches.first()

        if matching_user is None or not matching_user.check_password(form.password.data):
            # TODO: log bad invalid attempts
            flash("Invalid login credentials! Check your username and password.")
        else:
            login_user(matching_user)
            next_url = request.args.get('next')
            if next_url is None:
                return f"Welcome <b>{current_user.username}</b>!"
            else:
                return redirect(next_url)

    return render_template('login.html', form=form, error=error)

@app.route('/psa<int:psa_num>/')
@login_required
def display_results(psa_num):
    psa_str = 'psa' + str(psa_num)

    if psa_num == 0:
        q = (
            db_session.query(Student)
                .filter(Student.student_id == int(current_user.get_id()))
        )

        if q.count() == 1:
            the_student = q.first()
            repo_name = f"{course_name}-{term_name}-s{the_student.section_id:02}-{psa_str}"
            results_filename = f"/var/repos/{repo_name}/tester/{the_student.username}.html"

            if not os.path.isfile(results_filename):
                return f"""Your food file could not be found. Make sure it is
                correctly named as {the_student.username}.txt and that you have
                sync'ed your changes."""

            with open(results_filename, 'r') as results_file:
                return results_file.read()
        else:
            return f"{current_user.username}, you are not currently assigned to a section. Please contact your instructor."

    elif 1 <= psa_num <= 9:
        q = (
            db_session.query(Team.section_id, Team.team_num)
                .select_from(Student)
                .join(student_team)
                .join(Team)
                .filter(and_(Student.student_id == int(current_user.get_id()), Team.psa_id == psa_num))
        )

        if q.count() == 1:
            section_id, group_num = q.first()

            repo_name = f'{course_name}-{term_name}-s{section_id:02}-{psa_str}-group{group_num}'

            if not os.path.isfile(f"/var/repos/{repo_name}/tester/results.html"):
                return "Could not locate test results. Please contact your instructor."

            with open(f"/var/repos/{repo_name}/tester/results.html", 'r') as results_file:
                return results_file.read()
        else:
            return f'''<h1> Welcome {current_user.username}, you currently do not have an assigned group for {psa_str} </h1>'''
    else:
        abort(404)


@app.route('/logout/')
def logout():
    if current_user.is_authenticated:
        logout_user()
        return "You have successfully logged out!"
    else:
        return "You are not currently logged in."


@app.route("/")
def hello():
    return "Welcome to the Reliable Automated Feedback Test (RAFT) server."


def handle_requests(request_queue):
    """ Process function that waits for requests and runs tester when it
    receives one. """

    with open('/var/request-handler-errors.txt', 'a') as error_file:
        while True:
            sys.stdout.flush() # ensure we print out last iteration's stdout

            section_num, psa_num, group_num = request_queue.get()
            repo_name = f"{course_name}-{term_name}-s{section_num:02}-psa{psa_num}"

            if group_num is not None:
                repo_name += f"-group{group_num}"

            print(f"Handling request for {repo_name}")

            # check if we need to clone the repository first
            needs_pulled = True
            if not os.path.exists("/var/repos/" + repo_name):
                print("\tExisting repository not found. Cloning...")
                os.chdir("/var/repos/")
                result = subprocess.call(["git", "clone", "git@code:" + repo_name])

                if result != 0:
                    error_file.write(f"Could not clone: {repo_name}\n")
                    continue

                needs_pulled = False # fresh clone so don't need to pull later

            os.chdir("/var/repos/" + repo_name)

            # Pull latest changes, if necessary
            if needs_pulled:
                print("\tPulling from repository...")
                if subprocess.call(["git", "pull"]) != 0:
                    error_file.write(f"Could not pull: {repo_name}\n")
                    continue

            # check if the tester code directory exists, creating it if
            # necessary
            if not os.path.exists("tester"):
                print("\tSetting up tester directory...")
                result = subprocess.call(["cp", "-r", f"/var/tester_code/psa{psa_num}", "tester"])
                if result != 0:
                    error_file.write(f"Could not copy tester code: {repo_name}\n")
                    continue

            # copy over the student's code and run the tester
            db_query = (
                db_session.query(SourceFile.filename)
                    .join(PSA.files)
                    .filter(PSA.psa_id == psa_num)
                    .all()
            )

            files_under_test = []
            for result in db_query:
                if '*' in result.filename:
                    # if this contains a wildcard, use glob to get list of
                    # matching files
                    from glob import glob
                    files_under_test += glob(result.filename)
                else:
                    files_under_test.append(result.filename)


            cp_args = ["cp"] + files_under_test + ["tester/"]
            if subprocess.call(cp_args) != 0:
                error_file.write(f"Could not copy {', '.join(files_under_test)}: {repo_name}\n")
                continue

            os.chdir("tester/")
            print("\tRunning grader...")
            try:
                # TODO: make the timeout time a property of the assignment (e.g.
                # takes around 20 seconds will others are only a few seconds)
                if psa_num == 8:
                    timeout_length = 60
                else:
                    timeout_length = 15

                result = subprocess.run(["python3", "my_autograde.py"], capture_output=True, timeout=timeout_length)
                output_text = result.stdout
                error_text = result.stderr
                print(f"\tGrader finished with status code {result.returncode}")
            except subprocess.TimeoutExpired as e:
                output_text = e.stdout
                error_text = e.stderr
                print(f"\tGrader timed out after {e.timeout} seconds")

            with open("stdout.txt", "wb") as stdout_file, open("stderr.txt", "wb") as stderr_file:
                if output_text is not None:
                    stdout_file.write(output_text)
                if error_text is not None:
                    stderr_file.write(error_text)
	

if __name__ == "__main__":
    os.mkdir("/var/repos")

    # start 4 worker processes to handle running tests
    for _ in range(4):
        p = Process(target=handle_requests, args=(shared_queue,))
        p.start()

    app.run(host="0.0.0.0", port=6000)
