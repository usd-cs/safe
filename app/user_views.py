import os
import secrets
import string
import json
import csv

from sqlalchemy import insert, delete, and_

from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash, Markup
)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    StringField, SubmitField, IntegerField, MultipleFileField, SelectField,
    SelectMultipleField, BooleanField
)
from wtforms.validators import DataRequired, Regexp, NumberRange 
from wtforms.widgets import CheckboxInput
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from . import db_models
from . import admin

from app.helper import get_formatted_file_contents

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
                            user=current_user), 404

@user_views.app_errorhandler(403)
def permission_denied(error):
    return render_template("forbidden.html",
                            page_title="403: SAFE @ USD",
                            user=current_user), 403


class NewAssignmentForm(FlaskForm):
    assignment_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
    base_assignment_id = SelectField('Base Assignment', coerce=int)
    submit = SubmitField("Create Assignment")


class RosterUploadForm(FlaskForm):
    roster_file = FileField('Class Roster', validators=[FileRequired()])
            #validators=[Regexp('^.*\.(csv|CSV)$', message="Must be CSV file format")])
    add_drop = BooleanField('Enable Add/Drop')
    submit = SubmitField('Upload Roster')


def add_students_from_roster(section, file_location, session, add_drop=False):
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
                students_in_file = []

                initial_roster = (
                    session.query(db_models.User)
                        .join(db_models.Section.users)
                        .filter(db_models.Section.section_id == section.section_id)
                        .filter(db_models.User.instructor == False)
                        .all()
                )

                if not initial_roster:
                    initial_roster = []

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

                        student_to_add = db_models.User(username=username,
                                                        first_name=first_name,
                                                        last_name=last_name,
                                                        instructor=False,
                                                        admin=False)
                        session.add(student_to_add)
                        session.flush()

                    students_in_file.append(student_to_add)

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

                if add_drop:
                    # Find and remove students who were in the roster before but
                    # weren't part of the roster file.
                    students_to_remove = [s for s in initial_roster 
                                                if s not in students_in_file]

                    for student in students_to_remove:
                        # remove student from section
                        section.users.remove(student)

                        # remove student from section teams they may be in
                        teams_with_student = (
                            session.query(db_models.Team)
                                .join(db_models.Section.assignments)
                                .join(db_models.Assignment.teams)
                                .join(db_models.Team.members)
                                .filter(db_models.Section.section_id == section.section_id)
                                .filter(db_models.User.user_id == student.user_id)
                        )

                        for team in teams_with_student:
                            team.members.remove(student)

                    session.commit()

                    if len(students_to_remove) > 0:
                        flash(f"Removed {len(students_to_remove)} students from section.", "warning")

                if len(new_students) > 0:
                    flash(f"Added {len(new_students)} new students to section.", "info")
                if len(duplicate_students) > 0:
                    flash(f"Skipped {len(duplicate_students)} who were already enrolled.", "warning")
    
    except UnicodeError as e:
        flash(f"Roster file has incorrect encoding. Did you download it from Blackboard?", "danger")
        print("Error Opening file:", e)


class RemoveStudentsForm(FlaskForm):
    students_to_remove = SelectMultipleField('Student(s) to Remove', 
                                                coerce=int,
                                                option_widget=CheckboxInput(), 
                                                validators=[DataRequired()])
    submit = SubmitField("Remove Selected Students")


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
            # Construct the student's view of this page
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
                session.query(db_models.Assignment.num, db_models.BaseAssignment.title, db_models.Team.team_num)
                    .join(db_models.Section.assignments)
                    .join(db_models.Assignment.teams)
                    .filter(db_models.Section.section_id == section.section_id)
            )

            teams_with_user = (
                session.query(db_models.Assignment.num, db_models.BaseAssignment.title, db_models.Team.team_num)
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
        new_assignment_failed = False

        base_choices = [(ba.assignment_id, ba.title) 
                            for ba in session.query(db_models.BaseAssignment.assignment_id, db_models.BaseAssignment.title)]
        new_assignment_form.base_assignment_id.choices = base_choices

        if new_assignment_form.validate_on_submit():
            # TODO: make this a forms validator so error shows up next to fields
            # rather than a flash at the top after submitting
            num_matches = (
                    session.query(db_models.Assignment)
                        .filter(db_models.Assignment.section_id == section.section_id)
                        .filter(db_models.Assignment.num == new_assignment_form.assignment_num.data)
                        .count()
            )

            if num_matches != 0:
                flash(f"Assignment {new_assignment_form.assignment_num.data} already exists!", "danger")

            else:
                # create new assignment based on the selected base assignment
                # and add it to our database
                new_assignment = db_models.Assignment(num=new_assignment_form.assignment_num.data,
                                                        section_id=section.section_id,
                                                        base_assignment_id=new_assignment_form.base_assignment_id.data)

                session.add(new_assignment)
                session.commit()

                flash(f"PSA {new_assignment_form.assignment_num.data} ({new_assignment.base_assignment.title}) created!",
                        "info")

                return redirect(url_for(f'.section_overview', semester=semester, section_num=section_num))

        elif request.method == 'POST' and request.form['submit'] == "Create Assignment":
            # form was submitted but validation failed so tell template so it
            # can pop the modal up again
            new_assignment_failed = True


        remove_students_form = RemoveStudentsForm()

        enrolled_students = (
            session.query(db_models.User)
                .join(db_models.Section.users)
                .filter(db_models.Section.section_id == section.section_id)
                .filter(db_models.User.instructor == False)
                .all()
        )

        all_enrolled_students = [(s.user_id, s.username) for s in enrolled_students]
        remove_students_form.students_to_remove.choices = all_enrolled_students

        roster_upload_failed = False

        if remove_students_form.validate_on_submit():
            for student_id in remove_students_form.students_to_remove.data:
                print("removing student with ID", student_id)

                student = (
                    session.query(db_models.User)
                        .filter(db_models.User.user_id == student_id)
                        .first()
                )

                if not student:
                    # if we don't find that student, something bad happened so
                    # send 500 response
                    abort(500)

                # TODO: Use section.users.remove for simplicity
                s = delete(db_models.section_enrollment).where(and_(
                        db_models.section_enrollment.c.section_id == section.section_id,
                        db_models.section_enrollment.c.user_id == student_id))
                session.execute(s)

                # TODO: change this to return teams that the student is a member of
                student_team_enrollments = (
                    session.query(db_models.team_enrollment)
                        .join(db_models.Team)
                        .join(db_models.Assignment)
                        .join(db_models.Section)
                        .filter(db_models.Section.section_id == section.section_id)
                        .filter(db_models.team_enrollment.c.user_id == student_id)
                )

                # TODO: Use team.members.remove for simplicity
                for t in student_team_enrollments:
                    s = delete(db_models.team_enrollment).where(and_(
                            db_models.team_enrollment.c.team_id == t.team_id,
                            db_models.team_enrollment.c.user_id == t.user_id))
                    session.execute(s)

                    # TODO: remove teams that no longer have any members after
                    # removing this student???

                session.commit()


            return redirect(url_for(f'.section_overview', semester=semester, section_num=section_num))

        elif request.method == 'POST' and request.form['submit'] == "Upload Roster":
            # form was submitted but validation failed so tell template so it
            # can pop the modal up again
            roster_upload_failed = True

        remove_students_form.students_to_remove.choices = all_enrolled_students

        roster_upload_form = RosterUploadForm()

        if roster_upload_form.validate_on_submit():
            # add users to database
            uploaded_file = roster_upload_form.roster_file.data

            # save uploaded file to temporary file
            filename = secure_filename(uploaded_file.filename)

            temp_dir = file_location = os.path.join(current_app.instance_path, 'tmp')
            os.makedirs(temp_dir, exist_ok=True)

            file_location = os.path.join(temp_dir, filename)
            uploaded_file.save(file_location)

            add_students_from_roster(section, file_location, session,
                                        add_drop=roster_upload_form.add_drop.data)

            os.remove(file_location)
            return redirect(url_for(f'.section_overview', semester=semester, section_num=section_num))

        return render_template("section_overview.html", 
                                page_title="Section Overview: SAFE @ USD",
                                user=current_user,
                                section=section,
                                assignment_form=new_assignment_form,
                                remove_students_form=remove_students_form,
                                roster_form=roster_upload_form,
                                new_assignment_failed=new_assignment_failed,
                                roster_upload_failed=roster_upload_failed
                                )


@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/modify", methods=['get', 'post'])
@login_required
def modify_group(semester, section_num, psa_num, group_num):
    # TODO: remove repeated code between this and delete_group
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

        students_without_groups = get_students_without_groups(section.section_id, 
                                                                team.assignment.assignment_id)

        available_students_ids = [s.user_id for s in students_without_groups]
        available_students_names = [f"{s.last_name}, {s.first_name} ({s.username})" 
                                    for s in students_without_groups]

        existing_members_ids = [member.user_id for member in team.members]
        existing_members_names = [f"{member.last_name}, {member.first_name} ({member.username})" 
                                    for member in team.members]
        
        all_form_ids = existing_members_ids + available_students_ids
        all_form_names = existing_members_names + available_students_names

        # create list of (id, name) pairs, sorted by name
        all_options = sorted(zip(all_form_ids, all_form_names), key=lambda x: x[1])

        update_members_form = UpdateGroupMembersForm()
        update_members_form.members.choices = all_options

        if update_members_form.validate_on_submit():
            # add members that weren't previously selected
            for student_user_id in update_members_form.members.data:
                if student_user_id not in existing_members_ids:
                    new_member = (
                        session.query(db_models.User)
                            .filter(db_models.User.user_id == student_user_id)
                            .first()
                    )
                    team.members.append(new_member)

            # remove members that were selected previously but aren't now
            for student_user_id in existing_members_ids:
                if student_user_id not in update_members_form.members.data:
                    ex_member = (
                        session.query(db_models.User)
                            .filter(db_models.User.user_id == student_user_id)
                            .first()
                    )
                    team.members.remove(ex_member)

            session.commit()

            return redirect(url_for('.psa_overview', 
                                    semester=semester,
                                    section_num=section_num,
                                    psa_num=psa_num,
                                    group_num=group_num))


        #update_members_form.members.choices = zip(all_form_ids, available_students_names)
        update_members_form.members.choices = all_options
        update_members_form.members.data = [u.user_id for u in team.members]

        return render_template("modify_group_members.html",
                                page_title=f"Modify Group : SAFE @ USD",
                                user=current_user,
                                team=team,
                                form=update_members_form)



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


class UpdateGroupMembersForm(FlaskForm):
    members = admin.MultiCheckboxField('Group Member(s)', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")


@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/tester_files/<filename>")
@login_required
def view_tester_file(semester, section_num, psa_num, filename):
    with current_app.Session() as session:
        file_query = (
            session.query(db_models.Section, db_models.TesterFile)
                .join(db_models.Section.assignments)
                .join(db_models.BaseAssignment)
                .join(db_models.TesterFile)
                .filter(db_models.Section.course == "comp110")
                .filter(db_models.Section.semester == semester)
                .filter(db_models.Section.section_num == section_num)
                .filter(db_models.Assignment.num == psa_num)
                .filter(db_models.TesterFile.filename == filename)
        )


        if file_query.count() == 0:
            # Couldn't find the requested file
            abort(404)

        section, tester_file = file_query.first()

        if not (current_user.admin or 
                (current_user.instructor and current_user in section.users)):
            # Only admin's and this section's instructors can view
            # Note: we 404 rather than 403 here to hide filenames from peekers
            abort(404)

        formatted_file = get_formatted_file_contents(tester_file)

        # TODO: send md5sum and creation date to template

        return render_template("file_viewer.html", 
                                user=current_user,
                                filename=tester_file.filename,
                                file_contents=formatted_file)

def get_students_without_groups(section_id, assignment_id):
    with current_app.Session() as session:
        enrolled_students = (
            session.query(db_models.User)
                .join(db_models.section_enrollment)
                .join(db_models.Section)
                .filter(and_(db_models.Section.section_id == section_id, 
                                db_models.User.instructor == False))
        )

        students_in_groups = (
            session.query(db_models.User)
                .join(db_models.team_enrollment)
                .join(db_models.Team)
                .filter(db_models.Team.assignment_id == assignment_id)
        )

        students_without_groups = (
                enrolled_students
                    .except_(students_in_groups)
                    .order_by(db_models.User.last_name)
                    .all()
        )

        return students_without_groups

class CopyGroupsForm(FlaskForm):
    assignment_num = SelectField('Assignment', coerce=int)
    submit = SubmitField("Copy Groups")


# TODO: generalize for non comp110-courses
@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/", methods=['get', 'post'])
@login_required
def psa_overview(semester, section_num, psa_num):

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


        students_without_groups = get_students_without_groups(section.section_id, 
                                                                assignment.assignment_id)

        unassigned_students_ids = [s.user_id for s in students_without_groups]
        unassigned_students_names = [f"{s.last_name}, {s.first_name} ({s.username})" 
                        for s in students_without_groups]

        new_group_form = NewGroupForm()
        new_group_form.members.choices = zip(unassigned_students_ids,
                                                unassigned_students_names)

        if new_group_form.validate_on_submit():
            if new_group_form.group_num.data in [t.team_num for t in assignment.teams]:
                flash("That group number is already taken. Please select another.",
                        "danger")

            else:
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

        copy_groups_form = CopyGroupsForm()

        other_assignments = (
            session.query(db_models.Assignment)
                .join(db_models.Section.assignments)
                .filter(db_models.Section.section_id == section.section_id)
                .filter(db_models.Assignment.assignment_id != assignment.assignment_id)
                .order_by(db_models.Assignment.num.desc())
                .all()
        )

        copy_choices = [(a.num, f"PSA{a.num}: {a.base_assignment.title}") 
                            for a in other_assignments]

        copy_groups_form.assignment_num.choices = copy_choices

        if copy_groups_form.validate_on_submit():
            # Check that there aren't any existing teams in this assignment.
            # Note: The template should disable this form if there are existing
            # groups but want to be safe here.
            if len(assignment.teams) != 0:
                abort(500)

            groups = (
                session.query(db_models.Team)
                    .join(db_models.Section.assignments)
                    .join(db_models.Assignment.teams)
                    .filter(db_models.Section.section_id == section.section_id)
                    .filter(db_models.Assignment.num == copy_groups_form.assignment_num.data)
                    .all()
            )

            for g in groups:
                new_team = db_models.Team(team_num=g.team_num,
                                            assignment_id=assignment.assignment_id)

                for member in g.members:
                    new_team.members.append(member)

                session.add(new_team)

            session.commit()
            return redirect(url_for('.psa_overview', semester=semester, section_num=section_num, psa_num=psa_num))

        # TRICKY: validating form seems to clear out choices so have to
        # reset them here
        new_group_form.members.choices = zip(unassigned_students_ids,
                unassigned_students_names)

        copy_groups_form.assignment_num.choices = copy_choices

        return render_template("assignment_overview.html", 
                                user=current_user,
                                section=section,
                                assignment=assignment,
                                teams=assignment.teams,
                                group_form=new_group_form,
                                copy_groups_form=copy_groups_form)


@user_views.route("/comp110/psa<int:psa_num>/")
@login_required
def psa_results_shortcut(psa_num):
    # step 0: only for students (sorry and instructors and admins!)
    if current_user.admin or current_user.instructor:
        flash("Assignment shortcut link only available to students!", "warning")
        return redirect(url_for('.root'))

    with current_app.Session() as session:
        target_user = current_user

        # find any teams for the given course and psa
        matched_psa_info = (
            session.query(db_models.Section.semester, db_models.Section.section_num, db_models.Team.team_num)
                .join(db_models.Section.assignments)
                .join(db_models.Assignment.teams)
                .join(db_models.Team.members)
                .filter(db_models.Section.course == "comp110")
                .filter(db_models.Assignment.num == psa_num)
                .filter(db_models.User.username == target_user.username)
        )

        if matched_psa_info.count() == 0:
            # no teams found for this user
            flash(f"Could not find your group for COMP110 PSA {psa_num}. Check that you have a group listed when going to the section page.",
                    "danger")
            return redirect(url_for('.root'))

        elif matched_psa_info.count() > 1:
            # multiple teams found so redirect home but give them helpful direct
            # links
            section_links = ", ".join([f'<a href="{url_for(".psa_results", semester=semester, section_num=section_num, psa_num=psa_num, group_num=group_num)}">{semester}-s{section_num}-group{group_num}</a>' 
                for semester, section_num, group_num in matched_psa_info])

            message = Markup(f"You are enrolled in multiple groups for COMP110 PSA {psa_num}. Select among the following: {section_links}")
            flash(message, "warning")
            return redirect(url_for('.root'))

        else:
            # got a unique team so redirect to the correct results page
            semester, section_num, group_num = matched_psa_info.first()
        
            return redirect(url_for('.psa_results', 
                                    semester=semester,
                                    section_num=section_num,
                                    psa_num=psa_num,
                                    group_num=group_num))


@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
@login_required
def psa_results(semester, section_num, psa_num, group_num):
    with current_app.Session() as session:
        # TODO: combine the following queries into one!
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
                .order_by(db_models.TestResults.completed_at.desc())
                .first()
        )

        if not latest_test_results:
            # no test results available
            return render_template("assignment_results.html",
                                    user=current_user,
                                    assignment=assignment,
                                    group_num=group_num)

        raw_results = json.loads(latest_test_results.results)

        processed_results = {}
        for result in raw_results:
            category_results = processed_results.get(result["category_name"])

            if not category_results:
                # Haven't seen this category before so set basic structure up
                # for us (a dictionary with a few items) and add it to our
                # processed results
                category_results = {
                    "category_num": result["category_num"],
                    "category_name": result["category_name"],
                    "metrics": {}
                }

                processed_results[result["category_name"]] = category_results

            new_metric = {
                "description": result["metric"],
                "outcome": result["outcome"]
            }

            if "message" in result:
                new_metric["message"] = Markup(result["message"])

            category_results["metrics"][result["test_num"]] = new_metric


        categories = sorted(processed_results.values(), key=lambda c: c['category_num'])

        commit_time = f"{latest_test_results.commit_time: %b %d, %Y @ %I:%M:%S %p}"
        results_time = f"{latest_test_results.completed_at: %b %d, %Y @ %I:%M:%S %p}"

        return render_template("assignment_results.html",
                                user=current_user,
                                assignment=assignment,
                                group_num=group_num,
                                submit_time=commit_time,
                                results=latest_test_results,
                                results_time=results_time,
                                categories=categories)


@user_views.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/files/<filename>")
@login_required
def view_submitted_file(semester, section_num, psa_num, group_num, filename):
    job_id = request.args.get('id')
    if not job_id:
        abort(404)

    with current_app.Session() as session:
        submitted_file = (
            session.query(db_models.SubmittedFile)
                .join(db_models.TestResults.submitted_files)
                .filter(db_models.TestResults.job_id == job_id)
                .filter(db_models.SubmittedFile.filename == filename)
                .first()
        )

        if not submitted_file:
            abort(404)

        section, team = (
            session.query(db_models.Section, db_models.Team)
                .join(db_models.Section.assignments)
                .join(db_models.Assignment.teams)
                .filter(db_models.Section.course == "comp110")
                .filter(db_models.Section.semester == semester)
                .filter(db_models.Section.section_num == section_num)
                .filter(db_models.Assignment.num == psa_num)
                .filter(db_models.Team.team_num == group_num)
                .first()
        )


        if not (current_user.admin or 
                current_user in team.members or
                (current_user.instructor and current_user in section.users)):
            # Only admins, this section's instructors, and this group's members
            # may view the file.
            # Note: we 404 rather than 403 here to hide filenames from peekers
            abort(404)

        formatted_data = get_formatted_file_contents(submitted_file)

        # TODO: send md5sum and creation date to template

        return render_template("file_viewer.html", 
                                user=current_user,
                                filename=filename,
                                file_contents=formatted_data)
