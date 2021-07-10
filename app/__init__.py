import os
import json
from collections import namedtuple
import secrets, hashlib
import datetime
import string

# used for sending password recovery emails
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, redirect, url_for, abort, request, flash
from sqlalchemy import create_engine, inspect, insert, delete, and_, select
from sqlalchemy.orm import sessionmaker, with_parent, joinedload
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField, SelectMultipleField, IntegerField, BooleanField
from flask_wtf.file import FileField, FileRequired
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.validators import ValidationError, DataRequired, InputRequired, Length, AnyOf, Regexp, NumberRange, EqualTo
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, current_user, login_required

from . import admin
from . import auth

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

    from . import db
    from . import db_models
    db_engine = db.init_db(app)
    app.Session = sessionmaker(db_engine)

    app.register_blueprint(admin.admin, url_prefix="/admin")
    app.register_blueprint(auth.auth, url_prefix="/auth")


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


    @app.route('/profile/<username>')
    @login_required
    def user_profile(username):
        if not (current_user.admin or current_user.instructor or
                current_user.username == username):
            abort(403)

        with app.Session() as session:
            selected_user = (
                session.query(db_models.User)
                    .filter(db_models.User.username == username)
                    .first()
            )


            if selected_user:
                # if user exists, grab the list of classes they are enrolled in and
                # render the profile page view
                enrolled_courses = (
                    session.query(db_models.Section)
                        .join(db_models.section_enrollment)
                        .join(db_models.User)
                        .filter(db_models.User.username == selected_user.username)
                        .all()
                )

                # TODO: don't need DB query here... use the user's sections
                # field
                return render_template("user_profile.html",
                                        page_title=f"User Profile ({selected_user.username}) : SAFE @ USD",
                                        user=current_user,
                                        selected_user=selected_user,
                                        courses=enrolled_courses)
            else:
                # the user doesn't exist so 404 'em
                abort(404)

    @app.route('/')
    def root():
        return render_template("home.html", 
                                page_title="Home: SAFE @ USD",
                                user=current_user)

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("not_found.html", 
                                page_title="404: SAFE @ USD",
                                user=current_user)

    @app.errorhandler(403)
    def permission_denied(error):
        return render_template("forbidden.html",
                                page_title="403: SAFE @ USD",
                                user=current_user)

    class NewAssignmentForm(FlaskForm):
        assignment_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
        title = StringField('Assignment Title', validators=[DataRequired()])
        # TODO: add verification of correct format for assignment files (i.e.
        # space separated files)
        files = StringField('Assignment Files', validators=[DataRequired()])
        submit = SubmitField("Submit")

    class RosterUploadForm(FlaskForm):
        roster_file = FileField('Class Roster', validators=[FileRequired()])
                #validators=[Regexp('^.*\.(csv|CSV)$', message="Must be CSV file format")])
        submit = SubmitField('Upload Roster')

    # TODO: generalize for non-COMP110 courses
    @app.route('/comp110/<semester>/s<int:section_num>/', methods=['get', 'post'])
    @login_required
    def section_overview(semester, section_num):

        # TODO: split this function into two separate functions, which will be
        # called based on whether the user is a student or an instructor/admin
        with app.Session() as session:
            section = (
                session.query(db_models.Section)
                    .filter(db_models.Section.course == "comp110")
                    .filter(db_models.Section.semester == semester)
                    .filter(db_models.Section.section_num == section_num)
                    .first()
            )

            if not section:
                # section doesn't exist!
                abort(404)
            elif not (current_user.admin 
                        or (current_user in section.users)):
                # only admins and seciton instructor(s) can view this page.
                abort(403)

            if not (current_user.admin or current_user.instructor):
                instructors = (
                    session.query(db_models.User)
                        .join(db_models.Section.users)
                        .filter(db_models.Section.section_id == section.section_id)
                        .filter(db_models.User.instructor)
                        .all()
                )

                instructor_info = ", ".join([f"{u.first_name} {u.last_name} ({u.username}@sandiego.edu)" for u in instructors])

                # get intersection of section's assignments and user's teams
                # assignments
                teams_in_section = (
                    session.query(db_models.Assignment.num, db_models.Assignment.title, db_models.Team.team_num)
                        .join(db_models.Section.assignments)
                        .join(db_models.Assignment.teams)
                        .filter(db_models.Section.section_id == section.section_id)
                )

                teams_with_user = (
                    session.query(db_models.Assignment.num, db_models.Assignment.title, db_models.Team.team_num)
                        .select_from(db_models.Team)
                        .join(db_models.User.teams)
                        .join(db_models.Assignment)
                        .filter(db_models.User.username == current_user.username)
                )

                assignment_info = teams_in_section.intersect(teams_with_user).all()

                # render view for a student user
                return render_template("section_overview_student.html", 
                                        page_title="Section Overview: SAFE @ USD",
                                        user=current_user,
                                        section=section,
                                        instructors=instructor_info,
                                        assignments=assignment_info
                                        )

            new_assignment_form = NewAssignmentForm()
            roster_upload_form = RosterUploadForm()

            if new_assignment_form.validate_on_submit():
                num_matches = (
                        session.query(db_models.Assignment)
                            .filter(db_models.Assignment.section_id == section.section_id)
                            .filter(db_models.Assignment.num == new_assignment_form.assignment_num.data)
                            .count()
                )

                if num_matches != 0:
                    flash(f"Assignment {new_assignment_form.assignment_num.data} already exists!", "danger")

                else:
                    # create new assignment for DB
                    new_assignment = db_models.Assignment(num=new_assignment_form.assignment_num.data,
                                                            title=new_assignment_form.title.data,
                                                            section_id=section.section_id)

                    session.add(new_assignment)
                    session.flush()

                    # create separete SourceFile entries for each source file
                    assignment_files = new_assignment_form.files.data.split()
                    
                    # TODO: check for duplicate filenames
                    for af in assignment_files:
                        new_file = db_models.SourceFile(filename=af,
                                                        assignment_id=new_assignment.assignment_id)
                        session.add(new_file)

                    session.commit()

                    flash(f"Assignment {new_assignment_form.assignment_num.data} added with {len(assignment_files)} files!", "info")

                    return redirect(url_for(f'section_overview', semester=semester, section_num=section_num))

            if roster_upload_form.validate_on_submit():
                # add users to database
                uploaded_file = roster_upload_form.roster_file.data

                # save uploaded file to temporary file
                filename = secure_filename(uploaded_file.filename)

                temp_dir = file_location = os.path.join(app.instance_path, 'tmp')
                if not os.path.isdir(temp_dir):
                    os.mkdir(temp_dir)

                file_location = os.path.join(temp_dir, filename)
                uploaded_file.save(file_location)

                new_students = []
                duplicate_students = []

                with open(file_location, 'r') as roster_data:
                    # TODO: switch over to using python's CSV module for reading
                    # CSV files
                    header = roster_data.readline().strip()
                    col_names = header.split(',')

                    try:
                        first_name_col = col_names.index("FirstName/Middle")
                        last_name_col = col_names.index("LastName")
                        email_col = col_names.index("Email")
                    except ValueError:
                        # Couldn't find 1+ expected columns so we have to give
                        # up and let the instructor know.
                        flash("Roster file format is invalid. Could not find columns for one or more of the following: FirstName/Middle, LastName, Email", "danger")

                        roster_data.close()
                        os.remove(file_location)
                        return redirect(url_for(f'section_overview', semester=semester, section_num=section_num))

                    for line in roster_data:
                        columns = line.strip().split(',')

                        username = columns[email_col].split("@")[0]
                        last_name = columns[last_name_col]
                        first_name = columns[first_name_col]

                        # look for an existing user with that username
                        student_to_add = (
                            session.query(db_models.User)
                                .filter(db_models.User.username == username).first()
                        )

                        if student_to_add:
                            # found the student already so no need to create a
                            # new User object
                            print(f"User with {username} already exists. Skipping creation!")
                        else:
                            # Create new User and add to database
                            print(f"Creating student user with username {username}")

                            alphabet = string.ascii_letters + string.digits
                            temporary_password = ''.join(secrets.choice(alphabet) for i in range(20))

                            student_to_add = db_models.User(username=username,
                                                            password=generate_password_hash(temporary_password),
                                                            first_name=first_name,
                                                            last_name=last_name,
                                                            instructor=False,
                                                            admin=False)
                            session.add(student_to_add)
                            session.flush()

                        if student_to_add in section.users:
                            # student is already enrolled in this section so
                            # nothing more to do
                            duplicate_students.append(student_to_add.username)
                        else:
                            # Add user to this section
                            new_students.append(student_to_add.username)
                            statement = (
                                insert(db_models.section_enrollment)
                                    .values(user_id=student_to_add.user_id, section_id=section.section_id)
                            )
                            session.execute(statement)

                        session.commit()

                os.remove(file_location)

                flash(f"Added {len(new_students)} new students to section.", "info")
                flash(f"{len(duplicate_students)} students were already enrolled section.", "warning")

                return redirect(url_for(f'section_overview', semester=semester, section_num=section_num))

            return render_template("section_overview.html", 
                                    page_title="Section Overview: SAFE @ USD",
                                    user=current_user,
                                    section=section,
                                    assignment_form=new_assignment_form,
                                    roster_form=roster_upload_form
                                    )

    @app.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/delete")
    @login_required
    def delete_group(semester, section_num, psa_num, group_num):
        with app.Session() as session:
            query_result = (
                session.query(db_models.Section, db_models.Team)
                    .join(db_models.Section.assignments)
                    .join(db_models.Assignment.teams)
                    .filter(db_models.Section.semester == semester)
                    .filter(db_models.Section.section_num == section_num)
                    .filter(db_models.Assignment.num == psa_num)
                    .filter(db_models.Team.team_num == group_num)
                    .first()
            )

            if query_result:
                section, team = query_result
            else:
                abort(404)

            # only instructors for this section may delete a group
            if not (current_user.instructor and current_user in section.users):
                abort(403)

            # delete this group from the database
            session.delete(team)
            session.commit()

            flash(f"Removed group {group_num} from PSA {psa_num}", "info")
            return redirect(url_for('psa_overview',
                                    semester=semester,
                                    section_num=section_num,
                                    psa_num=psa_num))


    class NewGroupForm(FlaskForm):
        group_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
        members = admin.MultiCheckboxField('Group Member(s)', coerce=int, validators=[DataRequired()])
        submit = SubmitField("Submit")

    # TODO: generalize for non comp110-courses
    @app.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/", methods=['get', 'post'])
    @login_required
    def psa_overview(semester, section_num, psa_num):
        new_group_form = NewGroupForm()

        with app.Session() as session:
            section = (
                session.query(db_models.Section)
                    .filter(db_models.Section.course == "comp110")
                    .filter(db_models.Section.semester == semester)
                    .filter(db_models.Section.section_num == section_num)
                    .first()
            )

            if not section:
                abort(404)
            elif not (current_user.admin 
                        or (current_user.instructor and current_user in section.users)):
                # only admins and section instructor(s) can view this page.
                abort(403)

            assignment = (
                    session.query(db_models.Assignment)
                        .filter(db_models.Assignment.section_id == section.section_id)
                        .filter(db_models.Assignment.num == psa_num)
                        .first()
            )

            if not assignment:
                # assignment doesn't exist!
                abort(404)

            enrolled_students = (
                session.query(db_models.User)
                    .join(db_models.section_enrollment)
                    .join(db_models.Section)
                    .filter(and_(db_models.Section.section_id == section.section_id, 
                                    db_models.User.instructor == False))
            )

            students_in_groups = (
                session.query(db_models.User)
                    .join(db_models.team_enrollment)
                    .join(db_models.Team)
                    .filter(db_models.Team.assignment_id == assignment.assignment_id)
            )

            students_without_groups = (
                    enrolled_students
                        .except_(students_in_groups)
                        .order_by(db_models.User.last_name)
                        .all()
            )

            id_list = [s.user_id for s in students_without_groups]
            name_list = [f"{s.last_name}, {s.first_name} ({s.username})" 
                            for s in students_without_groups]

            new_group_form.members.choices = zip(id_list, name_list)

            if new_group_form.validate_on_submit():
                # TODO: Check that group_num doesn't already exist
                new_group = db_models.Team(team_num=new_group_form.group_num.data,
                                                assignment_id=assignment.assignment_id)

                session.add(new_group)
                session.flush() # causes DB to give the new_group a team_id

                # add selected students to team
                for student_id in new_group_form.members.data:
                    statement = (
                        insert(db_models.team_enrollment)
                            .values(user_id=student_id, team_id=new_group.team_id)
                    )
                    session.execute(statement)

                session.commit()

                return redirect(url_for('psa_overview', semester=semester, section_num=section_num, psa_num=psa_num))

            print("new group form errors:", new_group_form.errors)

            # TRICKY: validating form seems to clear out choices so have to
            # reset them here
            new_group_form.members.choices = zip(id_list, name_list)

            return render_template("assignment_overview.html", 
                                    user=current_user,
                                    section=section,
                                    assignment=assignment,
                                    teams=assignment.teams,
                                    group_form=new_group_form)


    TestResult = namedtuple('TestResult', ['status', 'summary', 'detail'])

    @app.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
    @login_required
    def psa_results(semester, section_num, psa_num, group_num):
        # TODO: validate semester, section num, psa_num, and group_num

        with app.Session() as session:
            section = (
                session.query(db_models.Section)
                    .filter(db_models.Section.course == "comp110")
                    .filter(db_models.Section.semester == semester)
                    .filter(db_models.Section.section_num == section_num)
                    .first()
            )

            if not section:
                abort(404)

            assignment = (
                    session.query(db_models.Assignment)
                        .filter(db_models.Assignment.section_id == section.section_id)
                        .filter(db_models.Assignment.num == psa_num)
                        .first()
            )

            if not assignment:
                abort(404)

            group = (
                    session.query(db_models.Team)
                        .filter(db_models.Team.assignment_id == assignment.assignment_id)
                        .filter(db_models.Team.team_num == group_num)
                        .first()
            )

            if not group:
                abort(404)
            elif not (current_user.admin 
                        or (current_user.instructor and current_user in section.users)
                        or (current_user in group.members)):
                # only admins, section instructor(s), and students in this group
                # can view this page.
                abort(403)
            
            # Read results from JSON file, filling them in a dictionary that is
            # organized by section.

            results = {}
            # FIXME: results file should depend on configured results directory
            # and course/semester/section/psa/group (maybe even just put these
            # in the database).
            results_json_location = os.path.join(app.instance_path, 'mock_results.json')
            with open(results_json_location, 'r') as results_file:

                json_results = json.load(results_file)
                for result in json_results["results"]:
                    section_results = results.get(result["section"])
                    new_test_result = TestResult(result["status"], result["summary"], result["detail"])

                    if section_results:
                        section_results.append(new_test_result)
                    else:
                        section_results = [new_test_result]

                    results[result["section"]] = section_results

                    print(result)

            return render_template("assignment_results.html",
                                    user=current_user,
                                    assignment=assignment,
                                    group_num=group_num,
                                    submit_time=json_results["submission_time"],
                                    commit_comment=json_results["commit_comment"],
                                    results_time=json_results["results_time"],
                                    test_results=results)

    class PasswordResetForm(FlaskForm):
        password = PasswordField('Password', validators=[InputRequired(),
                                                            Length(min=10, max=30),
                                                            EqualTo('confirm_password')])
        confirm_password = PasswordField('Repeat Password')
        submit = SubmitField('Submit')

    @app.route("/reset_password", methods=['get', 'post'])
    def reset_password():
        token = request.args.get('token')
        if not token:
            return render_template("bad_token.html",
                                    invalid_reason="Missing token")

        hashed_token = hashlib.sha1(token.encode('utf-8')).hexdigest()

        with app.Session() as session:
            existing_request = (
                session.query(db_models.PasswordResetRequest)
                    .filter(db_models.PasswordResetRequest.hashed_id == hashed_token)
                    .first()
            )

            if not existing_request:
                return render_template("bad_token.html",
                                        invalid_reason="Token does not exist")

            # check expiry date for password reset request
            time_diff = (datetime.datetime.now() - existing_request.time).total_seconds()

            if time_diff > 60 * app.config['MAX_PASSWORD_RESET_TIME']:
                session.delete(existing_request)
                session.commit()

                return render_template("bad_token.html",
                                        invalid_reason="Token has expired!")

            form = PasswordResetForm()

            if form.validate_on_submit():
                # remove request from table and update User with new password
                session.delete(existing_request)
                session.commit()

                user = (
                    session.query(db_models.User)
                        .filter(db_models.User.user_id == existing_request.user_id)
                        .first()
                )

                if not user:
                    abort(500)

                user.password = generate_password_hash(form.password.data)
                session.commit()

                flash("Password has been successfully reset.", "info")
                return redirect(url_for('auth.login'))

            return render_template("reset_password.html",
                                    page_title="Password Reset: SAFE @ USD",
                                    form=form)

    class ForgotPasswordForm(FlaskForm):
        username = StringField('USD Username', validators=[DataRequired()])
        submit = SubmitField('Submit')

    def send_password_recovery_email(user, token, email_address=None):
        message = MIMEMultipart("alternative")
        message["Subject"] = "SAFE Password Reset Request"

        # TODO: use email.utils.formataddr for from/to/reply-to
        message["From"] = app.config['EMAIL_ACCOUNT']

        if email_address:
            to_address = email_address
        else:
            # TODO: make domain configurable
            to_address = user.username + "@sandiego.edu"

        message["To"] = to_address
        message["Reply-To"] = app.config['EMAIL_ACCOUNT_NOREPLY']

        reset_link = app.config['SERVER_BASE_URL'] + url_for('reset_password', token=token)

        message_text = f"""\
        We have received a request to reset your SAFE @ USD password.

        Please visit the following webpage within 15 minutes to reset your password.

        {reset_link}

        If you did not initiate this request, please contact your instructor immediately."""

        message_html = f"""\
        <html>
        <body>
        <p>We have received a request to reset your SAFE @ USD password.</p>

        <p>
        Please visit the following webpage within <strong>15 minutes</strong> to reset your password.
        </p>

        <p><a href="{reset_link}">{reset_link}</a></p>

        <p>If you did not initiate this request, please contact your instructor
        immediately.</p>

        </body>
        </html>"""

        part1 = MIMEText(message_text, "plain")
        part2 = MIMEText(message_html, "html")
        message.attach(part1)
        message.attach(part2)

        context = ssl.create_default_context()
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as server:
            server.starttls(context=context)
            server.login(app.config['EMAIL_ACCOUNT'], app.config['SMTP_PASSWORD'])
            server.sendmail(app.config['EMAIL_ACCOUNT'],
                                        user.username + "@sandiego.edu",
                                        message.as_string())


    def create_password_request(username, session, email_recipient=None):
        token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha1(token.encode('utf-8')).hexdigest()

        # TODO: log reset requests
        user = (
            session.query(db_models.User)
                .filter(db_models.User.username == username)
                .first()
        )

        if user:
            # TODO: see if there is an existing request and handle
            # appropriately

            if app.config['EMAIL_ENABLED']:
                send_password_recovery_email(user, token,
                                                email_address=email_recipient)
            else:
                print("Password reset URL:", 
                        app.config['SERVER_BASE_URL'] + url_for('reset_password', token=token))

            new_request = db_models.PasswordResetRequest(hashed_id=hashed_token,
                                                            user_id=user.user_id)

            session.add(new_request)
            session.commit()


    @app.route("/forgot_password", methods=['get', 'post'])
    def forgot_password():
        form = ForgotPasswordForm()

        if form.validate_on_submit():
            with app.Session() as session:
                create_password_request(form.username.data, session)

                flash(("An email has been sent to your USD email address with " 
                        "instructions on resetting your password. You have "
                        f"{app.config['MAX_PASSWORD_RESET_TIME']} minutes to "
                        "complete the process."), 
                        "warning")
                return redirect(url_for('root'))

        return render_template("forgot_password.html",
                                page_title="Forgot Password: SAFE @ USD",
                                form=form)
        
    return app
