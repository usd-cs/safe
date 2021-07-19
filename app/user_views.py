import os
from collections import namedtuple
import secrets
import string
import json
import csv

from sqlalchemy import insert, delete, and_

from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import StringField, SubmitField, IntegerField, MultipleFileField
from wtforms.validators import DataRequired, Regexp, NumberRange 
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from . import db_models
from . import admin

user_views = Blueprint('user_views', __name__)

@user_views.route('/profile/<username>')
@login_required
def user_profile(username):
    if not (current_user.admin or current_user.instructor or
            current_user.username == username):
        abort(403)

    with current_app.Session() as session:
        selected_user = (
            session.query(db_models.User)
                .filter(db_models.User.username == username)
                .first()
        )

        if selected_user:
            return render_template("user_profile.html",
                                    page_title=f"User Profile ({selected_user.username}) : SAFE @ USD",
                                    user=current_user,
                                    selected_user=selected_user)
        else:
            # the user doesn't exist so 404 'em
            abort(404)

@user_views.route('/')
def root():
    return render_template("home.html", 
                            page_title="Home: SAFE @ USD",
                            user=current_user)

@user_views.app_errorhandler(404)
def page_not_found(error):
    return render_template("not_found.html", 
                            page_title="404: SAFE @ USD",
                            user=current_user)

@user_views.app_errorhandler(403)
def permission_denied(error):
    return render_template("forbidden.html",
                            page_title="403: SAFE @ USD",
                            user=current_user)

class NewAssignmentForm(FlaskForm):
    assignment_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
    title = StringField('Assignment Title', validators=[DataRequired()])
    # TODO: add verification of correct format for assignment files (i.e.
    # space separated files)
    tester_run_command = StringField('Tester Run Command', validators=[DataRequired()])
    files = StringField('Assignment Files', validators=[DataRequired()])
    tester_files = MultipleFileField('Tester Files', validators=[DataRequired()])
    submit = SubmitField("Submit")


class RosterUploadForm(FlaskForm):
    roster_file = FileField('Class Roster', validators=[FileRequired()])
            #validators=[Regexp('^.*\.(csv|CSV)$', message="Must be CSV file format")])
    submit = SubmitField('Upload Roster')


def add_students_from_roster(section, file_location, session):
    """
    Adds students in a given roster file (CSV format) to the specified section.

    This will add new Users to the database if the student hasn't been created
    before.
    """
    try:
        with open(file_location, newline='', encoding='utf-8-sig') as roster_data:
            roster_reader = csv.reader(roster_data)
            header = next(roster_reader)

            try:
                # Figure out which column contains the relevant user data
                first_name_col = header.index("First Name")
                last_name_col = header.index("Last Name")
                username_col = header.index("Username")
            except ValueError:
                # Couldn't find at least one of the required columns
                flash("Roster file format is invalid. Could not find columns for one or more of the following: First Name, Last Name, Username", 
                        "danger")
            else:
                # Found all the columns we need to read through roster and add
                # them to the section.

                new_students = []
                duplicate_students = []

                for line in roster_reader:
                    username = line[username_col]
                    last_name = line[last_name_col]
                    first_name = line[first_name_col]

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

                if len(new_students) > 0:
                    flash(f"Added {len(new_students)} new students to section.", "info")
                if len(duplicate_students) > 0:
                    flash(f"Skipped {len(duplicate_students)} who were already enrolled.", "warning")
    
    except UnicodeError as e:
        flash(f"Roster file has incorrect encoding. Did you download it from Blackboard?", "danger")
        print("Error Opening file:", e)

# TODO: generalize for non-COMP110 courses
@user_views.route('/comp110/<semester>/s<int:section_num>/', methods=['get', 'post'])
@login_required
def section_overview(semester, section_num):

    # TODO: split this function into two separate functions, which will be
    # called based on whether the user is a student or an instructor/admin
    with current_app.Session() as session:
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
                                                        tester_run_command=new_assignment_form.tester_run_command.data,
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

                session.flush()

                # Create separate TesterFile entries for each uploaded tester
                # file and save files to a directory for workers to access.
                tester_files = request.files.getlist(new_assignment_form.tester_files.name)

                # FIXME: this should go to a more unique path, whose base dir is
                # part of the app configuration
                tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                                f"psa{new_assignment.num}")
                os.makedirs(tester_code_dir, exist_ok=True)

                for tf in tester_files:
                    # TODO: store tf.content_type attribute in DB
                    new_tester_file = db_models.TesterFile(filename=tf.filename,
                                                            data=tf.read(),
                                                            assignment_id=new_assignment.assignment_id)
                    session.add(new_tester_file)

                    # save to the tester code directory
                    filename = secure_filename(tf.filename)
                    file_location = os.path.join(tester_code_dir, filename)
                    with open(file_location, 'wb') as new_file:
                        new_file.write(new_tester_file.data)

                session.commit()

                flash(f"Assignment {new_assignment_form.assignment_num.data} added with {len(assignment_files)} assignment files and {len(tester_files)} tester files!", "info")

                return redirect(url_for(f'.section_overview', semester=semester, section_num=section_num))

        if roster_upload_form.validate_on_submit():
            # add users to database
            uploaded_file = roster_upload_form.roster_file.data

            # save uploaded file to temporary file
            filename = secure_filename(uploaded_file.filename)

            temp_dir = file_location = os.path.join(current_app.instance_path, 'tmp')
            os.makedirs(temp_dir, exist_ok=True)

            file_location = os.path.join(temp_dir, filename)
            uploaded_file.save(file_location)

            add_students_from_roster(section, file_location, session)

            os.remove(file_location)
            return redirect(url_for(f'.section_overview', semester=semester, section_num=section_num))

        return render_template("section_overview.html", 
                                page_title="Section Overview: SAFE @ USD",
                                user=current_user,
                                section=section,
                                assignment_form=new_assignment_form,
                                roster_form=roster_upload_form
                                )

@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/delete")
@login_required
def delete_group(semester, section_num, psa_num, group_num):
    with current_app.Session() as session:
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
        return redirect(url_for('.psa_overview',
                                semester=semester,
                                section_num=section_num,
                                psa_num=psa_num))


class NewGroupForm(FlaskForm):
    group_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
    members = admin.MultiCheckboxField('Group Member(s)', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")

# TODO: generalize for non comp110-courses
@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/", methods=['get', 'post'])
@login_required
def psa_overview(semester, section_num, psa_num):
    new_group_form = NewGroupForm()

    with current_app.Session() as session:
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

            return redirect(url_for('.psa_overview', semester=semester, section_num=section_num, psa_num=psa_num))

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

@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
@login_required
def psa_results(semester, section_num, psa_num, group_num):
    # TODO: validate semester, section num, psa_num, and group_num

    with current_app.Session() as session:
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

        latest_test_results = (
            session.query(db_models.TestResults)
                .filter(db_models.TestResults.team_id == group.team_id)
                .filter(db_models.TestResults.finished)
                .order_by(db_models.TestResults.commit_time.desc())
                .first()
        )

        if not latest_test_results:
            # no test results available
            return render_template("assignment_results.html",
                                    user=current_user,
                                    assignment=assignment,
                                    group_num=group_num)

        unprocess_results = json.loads(latest_test_results.results)

        processed_results = {}
        for result in unprocess_results:
            section_results = processed_results.get(result["section"])
            new_test_result = TestResult(result["status"], result["summary"], result["detail"])

            if section_results:
                section_results.append(new_test_result)
            else:
                section_results = [new_test_result]

            processed_results[result["section"]] = section_results

        commit_time = f"{latest_test_results.commit_time: %b %d, %Y @ %I:%M:%S %p}"
        results_time = f"{latest_test_results.completed_at: %b %d, %Y @ %I:%M:%S %p}"

        return render_template("assignment_results.html",
                                user=current_user,
                                assignment=assignment,
                                group_num=group_num,
                                submit_time=commit_time,
                                commit_comment=latest_test_results.commit_comment,
                                results_time=results_time,
                                test_results=processed_results)

