import os
import secrets
import string
import json
import csv
import datetime

from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash, Markup
)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (
    StringField, SubmitField, IntegerField, MultipleFileField, SelectField,
    SelectMultipleField, BooleanField
)
from wtforms.validators import (
    DataRequired, Regexp, NumberRange, ValidationError
)
from wtforms.fields import DateField, TimeField
from wtforms.widgets import CheckboxInput, HiddenInput, DateInput, TimeInput
from werkzeug.utils import secure_filename

from . import db_models
from . import admin

from app import db
from app.helper import get_formatted_file_contents
from app.db_models import (
    User, Section, BaseAssignment, Assignment, TesterFile, Team, TestResults,
    SubmittedFile
)

user_views = Blueprint('user_views', __name__)

@user_views.route('/profile/<username>')
@login_required
def user_profile(username):
    if not (current_user.admin or current_user.instructor or
            current_user.username == username):
        abort(403)

    selected_user = (
        User.query
            .filter(User.username == username)
            .first()
    )

    if selected_user:
        return render_template("user_profile.html",
                                page_title=f"({selected_user.username}) Profile",
                                selected_user=selected_user)
    else:
        # the user doesn't exist so 404 'em
        abort(404)


@user_views.route('/')
def root():
    return render_template("home.html",
                            page_title="Home")


@user_views.app_errorhandler(404)
def page_not_found(error):
    return render_template("not_found.html",
                            page_title="Page Not Found"), 404

@user_views.app_errorhandler(403)
def permission_denied(error):
    return render_template("forbidden.html",
                            page_title="Access Forbidden"), 403


class NewAssignmentForm(FlaskForm):
    assignment_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
    base_assignment_id = SelectField('Base Assignment', coerce=int)
    due_date = DateField('Due Date', widget=DateInput(), validators=[DataRequired()])
    due_time = TimeField('Due Time', widget=TimeInput(), validators=[DataRequired()])
    section_id = IntegerField('Section ID',
                                widget=HiddenInput(), 
                                validators=[NumberRange(min=0)])
    submit = SubmitField("Create Assignment")

    def validate_assignment_num(form, field):
        num_matches = (
                Assignment.query
                    .filter(Assignment.section_id == form.section_id.data)
                    .filter(Assignment.num == form.assignment_num.data)
                    .count()
        )

        if num_matches != 0:
            raise ValidationError("Number already in use")


class RosterUploadForm(FlaskForm):
    roster_file = FileField('Class Roster', 
                            validators=[FileRequired(),
                                        FileAllowed(['csv'], 'Roster file must be CSV format')])
    add_drop = BooleanField('Enable Add/Drop')
    submit = SubmitField('Upload Roster')


def add_students_from_roster(section, file_location, add_drop=False):
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
                    User.query
                        .join(Section.users)
                        .filter(Section.section_id == section.section_id)
                        .filter(User.instructor == False)
                        .all()
                )

                if not initial_roster:
                    initial_roster = []

                for line in roster_reader:
                    username = line[username_col]
                    last_name = line[last_name_col]
                    first_name = line[first_name_col]

                    # look for an existing user with that username
                    student_to_add = User.query.filter(User.username == username).first()

                    if student_to_add:
                        # found the student already so no need to create a
                        # new User object
                        current_app.logger.debug(f"User with {username} already exists. Skipping creation!")
                    else:
                        # Create new User and add to database
                        student_to_add = User(username=username,
                                                        first_name=first_name,
                                                        last_name=last_name,
                                                        instructor=False,
                                                        admin=False)
                        db.session.add(student_to_add)
                        db.session.commit()

                        current_app.logger.info(f"Created student user with username {username}")

                    students_in_file.append(student_to_add)

                    if student_to_add in section.users:
                        # student is already enrolled in this section so
                        # nothing more to do
                        duplicate_students.append(student_to_add.username)
                    else:
                        # Add user to this section
                        # FIXME: make this sane
                        new_students.append(student_to_add.username)
                        statement = (
                            db.insert(db_models.section_enrollment)
                                .values(user_id=student_to_add.user_id, section_id=section.section_id)
                        )
                        db.session.execute(statement)

                    current_app.logger.debug(f"Skipped (Already enrolled): {duplicate_students}")
                    current_app.logger.info(f"Enrolled: {new_students}")

                    db.session.commit()

                if add_drop:
                    # Find and remove students who were in the roster before but
                    # weren't part of the roster file.
                    students_to_remove = [s for s in initial_roster 
                                                if s not in students_in_file]

                    for student in students_to_remove:
                        # remove student from section
                        section.users.remove(student)
                        current_app.logger.info(f"Removed {student.username} from section {section.section_id}")

                        # remove student from section teams they may be in
                        teams_with_student = (
                            session.query(Team)
                                .join(Section.assignments)
                                .join(Assignment.teams)
                                .join(Team.members)
                                .filter(Section.section_id == section.section_id)
                                .filter(User.user_id == student.user_id)
                        )

                        for team in teams_with_student:
                            team.members.remove(student)
                            current_app.logger.debug(f"Removed from team {team.team_id}")

                    db.session.commit()

                    if len(students_to_remove) > 0:
                        flash(f"Removed {len(students_to_remove)} students from section.", "warning")

                if len(new_students) > 0:
                    flash(f"Added {len(new_students)} new students to section.", "info")
                if len(duplicate_students) > 0:
                    flash(f"Skipped {len(duplicate_students)} who were already enrolled.", "warning")
    
    except UnicodeError as e:
        current_app.logger.warning(f"Roster file has incorrect encoding.")
        flash(f"Roster file has incorrect encoding. Did you download it from Blackboard?", "danger")


class RemoveStudentsForm(FlaskForm):
    students_to_remove = SelectMultipleField('Student(s) to Remove', 
                                                coerce=int,
                                                option_widget=CheckboxInput(), 
                                                validators=[DataRequired()])
    submit = SubmitField("Remove Selected Students")


@user_views.route('/<course_name>/<semester>/s<int:section_num>/', methods=['get', 'post'])
@login_required
def section_overview(course_name, semester, section_num):

    # TODO: split this function into two separate functions, which will be
    # called based on whether the user is a student or an instructor/admin
    section = (
        Section.query
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
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
            User.query
                .join(Section.users)
                .filter(Section.section_id == section.section_id)
                .filter(User.instructor)
                .all()
        )

        instructor_info = ", ".join([f"{u.first_name} {u.last_name} ({u.username}@sandiego.edu)" for u in instructors])

        assignment_info = (
            db.session.query(Assignment.num, BaseAssignment.title, Team.team_num)
                .join(Section.assignments)
                .join(Assignment.teams)
                .join(Team.members)
                .filter(Section.section_id == section.section_id)
                .filter(User.user_id == current_user.user_id)
                .group_by(Assignment.num)
                .all()
        )

        # render view for a student user
        return render_template("section_overview_student.html",
                                page_title="Section Overview",
                                section=section,
                                instructors=instructor_info,
                                assignments=assignment_info)


    new_assignment_form = NewAssignmentForm(section_id=section.section_id)
    new_assignment_failed = False

    base_choices = [(ba.assignment_id, ba.title) 
                        for ba in db.session.query(BaseAssignment.assignment_id, BaseAssignment.title)]
    new_assignment_form.base_assignment_id.choices = base_choices

    if new_assignment_form.validate_on_submit():
        # combine due date and time into single datetime
        deadline = datetime.datetime.combine(new_assignment_form.due_date.data,
                                                new_assignment_form.due_time.data)

        # create new assignment based on the selected base assignment
        # and add it to our database
        new_assignment = Assignment(num=new_assignment_form.assignment_num.data,
                                                section_id=section.section_id,
                                                base_assignment_id=new_assignment_form.base_assignment_id.data,
                                                deadline=deadline)

        db.session.add(new_assignment)
        db.session.commit()

        flash(f"PSA {new_assignment_form.assignment_num.data} ({new_assignment.base_assignment.title}) created!",
                "info")

        return redirect(url_for('.section_overview',
                                course_name=course_name,
                                semester=semester,
                                section_num=section_num))

    elif request.method == 'POST' and request.form['submit'] == "Create Assignment":
        # form was submitted but validation failed so tell template so it
        # can pop the modal up again
        new_assignment_failed = True


    remove_students_form = RemoveStudentsForm()

    enrolled_students = (
        User.query
            .join(Section.users)
            .filter(Section.section_id == section.section_id)
            .filter(User.instructor == False)
            .all()
    )

    all_enrolled_students = [(s.user_id, s.username) for s in enrolled_students]
    remove_students_form.students_to_remove.choices = all_enrolled_students

    roster_upload_failed = False

    if remove_students_form.validate_on_submit():
        for student_id in remove_students_form.students_to_remove.data:

            student = User.query.filter(User.user_id == student_id).first()

            if not student:
                # if we don't find that student, something bad happened so
                # send 500 response
                current_app.logger.error(f"Student with ID {student_id} not found")
                abort(500)

            current_app.logger.info(f"Removing {student.username} from section")

            # FIXME: Use section.users.remove for simplicity
            s = db.delete(db_models.section_enrollment).where(db.and_(
                    db_models.section_enrollment.c.section_id == section.section_id,
                    db_models.section_enrollment.c.user_id == student_id))
            db.session.execute(s)

            # TODO: change this to return teams that the student is a member of
            student_team_enrollments = (
                db.session.query(db_models.team_enrollment)
                    .join(Team)
                    .join(Assignment)
                    .join(Section)
                    .filter(Section.section_id == section.section_id)
                    .filter(db_models.team_enrollment.c.user_id == student_id)
            )

            # FIXME: Use team.members.remove for simplicity
            for t in student_team_enrollments:
                s = db.delete(db_models.team_enrollment).where(db.and_(
                        db_models.team_enrollment.c.team_id == t.team_id,
                        db_models.team_enrollment.c.user_id == t.user_id))
                db.session.execute(s)
                current_app.logger.debug(f"Removed from team {t.team_id}")

                # TODO: remove teams that no longer have any members after
                # removing this student???

            db.session.commit()


        return redirect(url_for('.section_overview',
                                course_name=course_name,
                                semester=semester,
                                section_num=section_num))

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

        add_students_from_roster(section, file_location,
                                    add_drop=roster_upload_form.add_drop.data)

        os.remove(file_location)
        return redirect(url_for('.section_overview',
                                course_name=course_name,
                                semester=semester,
                                section_num=section_num))

    return render_template("section_overview.html",
                            page_title="Section Overview",
                            section=section,
                            assignment_form=new_assignment_form,
                            remove_students_form=remove_students_form,
                            roster_form=roster_upload_form,
                            new_assignment_failed=new_assignment_failed,
                            roster_upload_failed=roster_upload_failed)


@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/modify", methods=['get', 'post'])
@login_required
def modify_group(course_name, semester, section_num, psa_num, group_num):
    # TODO: remove repeated code between this and delete_group
    query_result = (
        db.session.query(Section, Team)
            .join(Section.assignments)
            .join(Assignment.teams)
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .filter(Assignment.num == psa_num)
            .filter(Team.team_num == group_num)
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
                new_member = User.query.filter(User.user_id == student_user_id).first()
                team.members.append(new_member)

        # remove members that were selected previously but aren't now
        for student_user_id in existing_members_ids:
            if student_user_id not in update_members_form.members.data:
                ex_member = User.query.filter(User.user_id == student_user_id).first()
                team.members.remove(ex_member)

        db.session.commit()

        return redirect(url_for('.psa_overview', 
                                course_name=course_name,
                                semester=semester,
                                section_num=section_num,
                                psa_num=psa_num,
                                group_num=group_num))


    #update_members_form.members.choices = zip(all_form_ids, available_students_names)
    update_members_form.members.choices = all_options
    update_members_form.members.data = [u.user_id for u in team.members]

    return render_template("modify_group_members.html",
                            page_title="Modify Group",
                            team=team,
                            form=update_members_form)



@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/delete")
@login_required
def delete_group(course_name, semester, section_num, psa_num, group_num):
    query_result = (
        db.session.query(Section, Team)
            .join(Section.assignments)
            .join(Assignment.teams)
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .filter(Assignment.num == psa_num)
            .filter(Team.team_num == group_num)
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
    db.session.delete(team)
    db.session.commit()

    flash(f"Removed group {group_num} from PSA {psa_num}", "info")
    return redirect(url_for('.psa_overview',
                            course_name=course_name,
                            semester=semester,
                            section_num=section_num,
                            psa_num=psa_num))




class NewGroupForm(FlaskForm):
    group_num = IntegerField('Group Number', validators=[NumberRange(min=0)])
    members = admin.MultiCheckboxField('Group Member(s)', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Create Group")


class UpdateGroupMembersForm(FlaskForm):
    members = admin.MultiCheckboxField('Group Member(s)', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Update Members")


@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/tester_files/<filename>")
@login_required
def view_tester_file(course_name, semester, section_num, psa_num, filename):
    file_query = (
        db.session.query(Section, TesterFile)
            .join(Section.assignments)
            .join(BaseAssignment)
            .join(TesterFile)
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .filter(Assignment.num == psa_num)
            .filter(TesterFile.filename == filename)
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
                            page_title=tester_file.filename,
                            filename=tester_file.filename,
                            file_contents=formatted_file)


def get_students_without_groups(section_id, assignment_id):
    enrolled_students = (
        User.query
            .join(db_models.section_enrollment)
            .join(Section)
            .filter(db.and_(Section.section_id == section_id, 
                            User.instructor == False))
    )

    students_in_groups = (
        User.query
            .join(db_models.team_enrollment)
            .join(Team)
            .filter(Team.assignment_id == assignment_id)
    )

    students_without_groups = (
            enrolled_students
                .except_(students_in_groups)
                .order_by(User.last_name)
                .all()
    )

    return students_without_groups

class CopyGroupsForm(FlaskForm):
    assignment_num = SelectField('Assignment', coerce=int)
    submit = SubmitField("Copy Groups")


@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/delete")
@login_required
def delete_assignment(course_name, semester, section_num, psa_num):
    query_results = (
        db.session.query(Section, Assignment)
            .join(Section.assignments)
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .filter(Assignment.num == psa_num)
            .first()
    )

    if not query_results:
        # couldn't find assignment
        abort(404)

    section, assignment = query_results

    if (not current_user.instructor) or (current_user not in section.users):
        # only permit instructors for this section
        abort(403)

    db.session.delete(assignment)
    db.session.commit()

    flash(f"Successfully deleted PSA {psa_num}", "info")

    return redirect(url_for('.section_overview',
                            course_name=course_name, semester=semester, section_num=section_num))



# TODO: generalize endpoint name so assignment initials don't have to be "psa"
@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/", methods=['get', 'post'])
@login_required
def psa_overview(course_name, semester, section_num, psa_num):

    section = (
        Section.query
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .first()
    )

    if not section:
        abort(404)
    elif not (current_user.admin 
                or (current_user.instructor and current_user in section.users)):
        # only admins and section instructor(s) can view this page.
        abort(403)

    assignment = (
            Assignment.query
                .filter(Assignment.section_id == section.section_id)
                .filter(Assignment.num == psa_num)
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
    new_group_form.members.choices = list(zip(unassigned_students_ids,
                                              unassigned_students_names))

    if new_group_form.validate_on_submit():
        if new_group_form.group_num.data in [t.team_num for t in assignment.teams]:
            flash("That group number is already taken. Please select another.",
                    "danger")

        else:
            new_group = Team(team_num=new_group_form.group_num.data,
                                            assignment_id=assignment.assignment_id)

            db.session.add(new_group)
            db.session.commit() # causes DB to give the new_group a team_id

            # add selected students to team
            for student_id in new_group_form.members.data:
                # FIXME: make this sane
                statement = (
                    db.insert(db_models.team_enrollment)
                        .values(user_id=student_id, team_id=new_group.team_id)
                )
                db.session.execute(statement)

            db.session.commit()

            return redirect(url_for('.psa_overview', course_name=course_name, semester=semester, section_num=section_num, psa_num=psa_num))

    copy_groups_form = CopyGroupsForm()

    other_assignments = (
        Assignment.query
            .join(Section.assignments)
            .filter(Section.section_id == section.section_id)
            .filter(Assignment.assignment_id != assignment.assignment_id)
            .order_by(Assignment.num.desc())
            .all()
    )

    copy_choices = [(a.num, f"PSA{a.num}: {a.base_assignment.title}") 
                        for a in other_assignments]

    copy_groups_form.assignment_num.choices = copy_choices

    if copy_groups_form.validate_on_submit():
        # Check that there aren't any existing teams in this assignment.
        # Note: The template should disable this form if there are existing
        # groups but want to be safe here.
        if assignment.teams.count() != 0:
            abort(500)

        groups = (
            Team.query
                .join(Section.assignments)
                .join(Assignment.teams)
                .filter(Section.section_id == section.section_id)
                .filter(Assignment.num == copy_groups_form.assignment_num.data)
                .all()
        )

        for g in groups:
            new_team = Team(team_num=g.team_num,
                                        assignment_id=assignment.assignment_id)

            for member in g.members:
                new_team.members.append(member)

            db.session.add(new_team)

        db.session.commit()
        return redirect(url_for('.psa_overview', course_name=course_name, semester=semester, section_num=section_num, psa_num=psa_num))

    # TRICKY: validating form seems to clear out choices so have to
    # reset them here
    new_group_form.members.choices = list(zip(unassigned_students_ids,
                                              unassigned_students_names))

    copy_groups_form.assignment_num.choices = copy_choices

    return render_template("assignment_overview.html",
                           page_title="Assignment Overview",
                           section=section,
                           assignment=assignment,
                           group_form=new_group_form,
                           copy_groups_form=copy_groups_form)


@user_views.route("/<course_name>/psa<int:psa_num>/")
@login_required
def psa_results_shortcut(course_name, psa_num):
    # step 0: only for students (sorry and instructors and admins!)
    if current_user.admin or current_user.instructor:
        flash("Assignment shortcut link only available to students!", "warning")
        return redirect(url_for('.root'))

    target_user = current_user

    # find any teams for the given course and psa
    matched_psa_info = (
        db.session.query(Section.semester, Section.section_num, Team.team_num)
            .join(Section.assignments)
            .join(Assignment.teams)
            .join(Team.members)
            .filter(Section.course == course_name)
            .filter(Assignment.num == psa_num)
            .filter(User.username == target_user.username)
    )

    if matched_psa_info.count() == 0:
        # no teams found for this user
        flash(f"Could not find your group for COMP110 PSA {psa_num}. Check that you have a group listed when going to the section page.",
                "danger")
        return redirect(url_for('.root'))

    elif matched_psa_info.count() > 1:
        # multiple teams found so redirect home but give them helpful direct
        # links
        section_links = ", ".join([f'<a href="{url_for(".psa_results", course_name=course_name, semester=semester, section_num=section_num, psa_num=psa_num, group_num=group_num)}">{semester}-s{section_num}-group{group_num}</a>' 
            for semester, section_num, group_num in matched_psa_info])

        message = Markup(f"You are enrolled in multiple groups for COMP110 PSA {psa_num}. Select among the following: {section_links}")
        flash(message, "warning")
        return redirect(url_for('.root'))

    else:
        # got a unique team so redirect to the correct results page
        semester, section_num, group_num = matched_psa_info.first()

        return redirect(url_for('.psa_results', 
                                course_name=course_name,
                                semester=semester,
                                section_num=section_num,
                                psa_num=psa_num,
                                group_num=group_num))


@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
@login_required
def psa_results(course_name, semester, section_num, psa_num, group_num):
    # TODO: combine the following queries into one!
    section = (
        Section.query
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .first()
    )

    if not section:
        abort(404)

    assignment = section.assignments.filter_by(num=psa_num).first()

    if not assignment:
        abort(404)

    group = assignment.teams.filter_by(team_num=group_num).first()

    if not group:
        abort(404)

    elif not (current_user.admin
                or (current_user.instructor and current_user in section.users)
                or (current_user in group.members)):
        # only admins, section instructor(s), and students in this group
        # can view this page.
        abort(403)

    latest_test_results = group.get_latest_results()

    if not latest_test_results:
        # no test results available
        return render_template("assignment_results.html",
                               page_title="Assignment Results",
                               assignment=assignment,
                               group_num=group_num)

    processed_results = latest_test_results.process_results()

    categories = sorted(processed_results.values(), key=lambda c: c['category_num'])

    commit_time = f"{latest_test_results.commit_time: %b %d, %Y @ %I:%M:%S %p}"

    # add a late notice to time string
    if latest_test_results.commit_time > assignment.deadline:
        commit_time += " (<span class=\"text-danger\"><strong>LATE</strong></span>)"

    commit_time = Markup(commit_time)

    results_time = f"{latest_test_results.completed_at: %b %d, %Y @ %I:%M:%S %p}"

    return render_template("assignment_results.html",
                           page_title="Assignment Results",
                           assignment=assignment,
                           group_num=group_num,
                           submit_time=commit_time,
                           results=latest_test_results,
                           results_time=results_time,
                           categories=categories)


@user_views.route("/<course_name>/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/files/<filename>")
@login_required
def view_submitted_file(course_name, semester, section_num, psa_num, group_num, filename):
    job_id = request.args.get('id')
    if not job_id:
        abort(404)

    submitted_file = (
        SubmittedFile.query
            .join(TestResults.submitted_files)
            .filter(TestResults.job_id == job_id)
            .filter(SubmittedFile.filename == filename)
            .first()
    )

    if not submitted_file:
        abort(404)

    section, team = (
        db.session.query(Section, Team)
            .join(Section.assignments)
            .join(Assignment.teams)
            .filter(Section.course == course_name)
            .filter(Section.semester == semester)
            .filter(Section.section_num == section_num)
            .filter(Assignment.num == psa_num)
            .filter(Team.team_num == group_num)
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
                           page_title=filename,
                           filename=filename,
                           file_contents=formatted_data)

