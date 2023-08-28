import os
import re

from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SubmitField, PasswordField, SelectMultipleField, IntegerField,
    BooleanField, SelectField, MultipleFileField
)
from flask_wtf.file import FileField, FileRequired
from wtforms.validators import (
    ValidationError, DataRequired, Length, NumberRange
)
from wtforms.widgets import ListWidget, CheckboxInput
from flask_login import (
    LoginManager, current_user, login_required
)
from werkzeug.utils import secure_filename
from . import db_models

from app import db
from app.helper import get_formatted_file_contents
from app.db_models import (
    User, Section, BaseAssignment, Assignment, TesterFile, SourceFile
)

admin = Blueprint('admin', __name__)


class NewInstructorForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    username = StringField('USD Username', validators=[DataRequired()])
    admin = BooleanField('Admin')
    submit = SubmitField('Create Instructor')

    def validate_username(form, field):
        if User.query.filter(User.username == field.data).count() != 0:
            raise ValidationError("An instructor with that username already exists")


@admin.route('/')
@login_required
def admin_home():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    return render_template("admin.html",
            page_title="Admin Home")


@admin.route('/users')
@login_required
def admin_users():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    all_users = User.query.order_by(User.last_name).all()

    return render_template("admin_users.html",
                            page_title="Admin Users",
                            users=all_users)


@admin.route('/instructors', methods=['get', 'post'])
@login_required
def admin_instructors():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)
        
    form = NewInstructorForm()

    if form.validate_on_submit():
        # add user to database
        new_instructor = User(username=form.username.data,
                                            first_name=form.first_name.data,
                                            last_name=form.last_name.data,
                                            admin=form.admin.data,
                                            instructor=True)
        db.session.add(new_instructor)
        db.session.commit()

        flash(f"Added new instructor: {new_instructor.first_name} {new_instructor.last_name}", "success")
        current_app.logger.info(f"Added new instructor: {new_instructor.first_name} {new_instructor.last_name}")

        return redirect(url_for('.admin_instructors'))

    # form wasn't valid so re-render the page
    instructors = (
        User.query
            .filter(User.instructor == True)
            .order_by(User.last_name)
    )

    return render_template("admin_instructors.html",
                            page_title="Admin Instructors",
                            form=form,
                            instructors=instructors)


# TODO: This is a generic form element so don't bury this in here
class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class NewSectionForm(FlaskForm):
    course = SelectField('Course',
                            choices=[
                                ('comp110', 'COMP110: Computational Problem Solving'),
                                ('comp120', 'COMP120: Programming Abstractions and Methodologies'),
                                ('comp230', 'COMP230: Advanced Computational Problem Modeling'),
                                ('comp280', 'COMP280: Intro to Computer Systems'),
                                ('comp300', 'COMP300: Principles of Digital Hardware'),
                                ('comp305', 'COMP305: Object-Oriented Design and Programming'),
                                ('comp370', 'COMP370: Automata, Computability and Formal Language'),
                                ('comp375', 'COMP375: Networking'),
                                ('comp480', 'COMP480: Algorithms')
                            ])
    semester = SelectField('Semester',
                            choices=[('fa', 'Fall'), ('sp', 'Spring')])
    year = IntegerField('Year', validators=[NumberRange(min=2020, max=2050)])
    section_num = IntegerField('Section Number', validators=[NumberRange(min=1)])
    instructors = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Create Section")


class ModifySectionForm(FlaskForm):
    instructors = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Update Instructors")


@admin.route('/sections/modify', methods=['get', 'post'])
@login_required
def modify_section():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    section_id = request.args.get('section_id')

    if not section_id:
        current_app.logger.error("Missing section_id")
        abort(404)
    else:
        try:
            section_id = int(section_id)
        except ValueError:
            flash(f"Invalid value for section_id: {section_id}", "danger")
            current_app.logger.error(f"Invalid section_id: {section_id}")
            return redirect(url_for('.admin_sections'))

    # verify there is a section with the given ID
    section = Section.query.filter_by(section_id=section_id).first()

    if not section:
        current_app.logger.error(f"No section found with id {section_id}")
        abort(404)

    form = ModifySectionForm()

    form.instructors.choices = get_instructor_choices()
    previous_instructors_ids = [i.user_id for i in section.instructors()]

    if form.validate_on_submit():
        current_app.logger.debug(f"selected instructors: {form.instructors.data}")

        selected_instructors = User.query.filter(User.user_id.in_(form.instructors.data))
        section.users = selected_instructors.all() + section.students()

        db.session.commit()
        current_app.logger.info(f"Updated instructors for section {section_id}")

        return redirect(url_for('.modify_section', section_id=section_id))

    # pre-fill old instructors into selections
    form.instructors.data = previous_instructors_ids[:]

    return render_template("modify_section.html",
                            page_title="Modify Section",
                            section=section,
                            form=form)


def get_instructor_choices():
    """ Returns list of tuples of (id, formatted name string) for all
    instructors. """
    all_instructors = User.query.filter_by(instructor=True)
    return [(i.user_id, f"{i.last_name}, {i.first_name} ({i.username})")
            for i in all_instructors]


@admin.route('/sections', methods=['get', 'post'])
@login_required
def admin_sections():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    form = NewSectionForm()

    all_sections = Section.query.order_by(Section.course,
                                                    Section.semester,
                                                    Section.section_num)

    instructor_choices = get_instructor_choices()
    form.instructors.choices = instructor_choices

    if form.validate_on_submit():
        semester = form.semester.data + str(form.year.data)[-2:]

        # TODO: Turn this isn't a form validator so error shows up closer to
        # where it matters (i.e. under the section field, not as a flash at
        # the top of the page.
        num_matching_sections = (
            Section.query
                .filter(Section.course == form.course.data)
                .filter(Section.semester == semester)
                .filter(Section.section_num == int(form.section_num.data))
                .count()
        )

        # make sure a section with given info doesn't already exist
        if num_matching_sections != 0:
            flash("A section with that information already exists!", "danger")
            form.instructors.choices = instructor_choices

            return render_template("admin_sections.html",
                                    page_title="Admin Sections",
                                    form=form,
                                    sections=all_sections)

        # create the new section and add it to the database
        new_section = Section(course=form.course.data,
                              semester=semester,
                              section_num=int(form.section_num.data),
                              users=User.query.filter(User.user_id.in_(form.instructors.data)))


        db.session.add(new_section)
        db.session.commit() # causes DB to give the new_section a section_id

        current_app.logger.info(f"Added new section (ID: {new_section.section_id}): {new_section.course.upper()}, Section {new_section.section_num} ({new_section.semester.upper()})")
        flash(f"Succesfully added new section: {new_section.course.upper()}, Section {new_section.section_num} ({new_section.semester.upper()})", "success")

        return redirect(url_for('.admin_sections'))

    if form.errors:
        current_app.logger.debug(f"form errors: {form.errors}")

    form.instructors.choices = instructor_choices

    return render_template("admin_sections.html",
                            page_title="Admin Sections",
                            form=form,
                            sections=all_sections)


def get_tester_file(assignment_id, filename):
    return (
        TesterFile.query
            .join(BaseAssignment.tester_files)
            .filter(BaseAssignment.assignment_id == assignment_id)
            .filter(TesterFile.filename == filename)
            .first()
    )


class AddTesterFilesForm(FlaskForm):
    new_files = MultipleFileField('New Tester Files', validators=[DataRequired()])
    submit = SubmitField("Add Files")


@admin.route("/assignments/<int:assignment_id>/tester_files/add", methods=['get','post'])
@login_required
def add_tester_files(assignment_id):
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    assignment = (
        BaseAssignment.query
            .filter(BaseAssignment.assignment_id == assignment_id)
            .first()
    )

    if not assignment:
        current_app.logger.warning(f"No assignment with id {assignment_id}")
        abort(404)

    add_files_form = AddTesterFilesForm()

    if add_files_form.validate_on_submit():
        # Create separate TesterFile entries for each uploaded tester
        # file and save files to a directory for workers to access.
        new_files = request.files.getlist(add_files_form.new_files.name)

        existing_tester_files = [tf.filename for tf in assignment.tester_files]

        skipped_files = []
        for tf in new_files:
            if tf.filename in existing_tester_files:
                # if there is already a file with this name, skip it
                skipped_files.append(tf.filename)
                current_app.logger.debug(f"Skipped existing file: {tf.filename}")
                continue

            # TODO: store tf.content_type attribute in DB
            new_tester_file = TesterFile(filename=tf.filename,
                                                   data=tf.read(),
                                                   base_assignment=assignment)
            db.session.add(new_tester_file)
            current_app.logger.info(f"Added {tf.filename} to assignment {assignment_id}")

            # save to the tester code directory
            new_tester_file.write_to_file(current_app.config['TESTER_CODE_BASE_DIR'])

        db.session.commit()

        if len(skipped_files) > 0:
            flash(f"The following files already exist and were skipped: {' '.join(skipped_files)}",
                    "warning")

        if len(new_files) > len(skipped_files):
            flash(f"Added {len(new_files) - len(skipped_files)} files to assignment '{assignment.title}'",
                    "success")

        return redirect(url_for('.admin_assignments'))


    return render_template("admin_add_tester_files.html",
                            page_title="Add Tester Files",
                            assignment=assignment,
                            files_form=add_files_form)


@admin.route("/assignments/<int:assignment_id>/tester_files/<filename>/delete")
@login_required
def delete_tester_file(assignment_id, filename):
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    tester_file = get_tester_file(assignment_id, filename)

    if not tester_file:
        current_app.logger.warning(f"{filename} is not a assignment {assignment_id} tester file")
        abort(404)

    tester_file.delete(current_app.config['TESTER_CODE_BASE_DIR'])

    current_app.logger.info(f"Removed {filename} from assignment {assignment_id} tester files")

    return redirect(url_for('.admin_assignments'))


class UpdateTesterFileForm(FlaskForm):
    tester_file = FileField('Replacement File', validators=[FileRequired()])
    submit = SubmitField('Replace File')


@admin.route("/assignments/<int:assignment_id>/tester_files/<filename>", methods=['get', 'post'])
@login_required
def view_tester_file(assignment_id, filename):
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    tester_file = get_tester_file(assignment_id, filename)

    if not tester_file:
        current_app.logger.warning(f"{filename} is not a assignment {assignment_id} tester file")
        abort(404)

    update_file_form = UpdateTesterFileForm()

    if update_file_form.validate_on_submit():
        # add users to database
        uploaded_file = update_file_form.tester_file.data
        sec_filename = secure_filename(uploaded_file.filename)

        if sec_filename == filename:
            # update file contents in database
            tester_file.data = uploaded_file.read()
            db.session.commit()

            # save uploaded file to tester code directory
            tester_file.write_to_file(current_app.config['TESTER_CODE_BASE_DIR'])

            flash("File has been updated!", "success")
            current_app.logger.info(f"{filename} has been updated in assignment {assignment_id}")

        else:
            current_app.logger.debug(f"Uploaded file {sec_filename} does not match filename ({filename})")
            flash(f"Uploaded filename ({sec_filename}) differs from this file.", "danger")


    formatted_file = get_formatted_file_contents(tester_file)

    # TODO: send md5sum and creation date to template

    return render_template("file_viewer.html",
                           page_title=tester_file.filename,
                           filename=tester_file.filename,
                           file_contents=formatted_file,
                           update_file_form=update_file_form)


@admin.route("/users/delete")
@login_required
def admin_delete_user():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)
        
    user_id = request.args.get('id')

    # if user id wasn't specified, just redirect to admin page for users
    if not user_id:
        current_app.logger.error("Failed: Missing user id")
        flash("Could not delete user. ID missing.", "danger")
    else:
        user = User.query.filter(User.user_id == int(user_id)).first()

        if not user:
            current_app.logger.error(f"Failed: Invalid user ID ({user_id})")
            flash("Could not delete user. Invalid ID.", "danger")
        else:
            current_app.logger.info(f"Deleted user {user.username}")
            flash(f"Successfully deleted user {user.username}", "success")
            db.session.delete(user)
            db.session.commit()

    return redirect(url_for('.admin_users'))


class NewAssignmentForm(FlaskForm):
    title = StringField('Assignment Title', validators=[DataRequired()])
    tester_run_command = StringField('Tester Run Command', validators=[DataRequired()])

    files = StringField('Assignment Files', validators=[DataRequired()])
    tester_files = MultipleFileField('Tester Files', validators=[DataRequired()])
    max_runtime = IntegerField('Maximum Test Runtime', validators=[NumberRange(min=1)])
    submit = SubmitField("Create Assignment")

    def validate_title(form, field):
        """ Validate that title isn't already used by an assignment. """
        if BaseAssignment.query.filter(BaseAssignment.title == field.data).count() != 0:
            raise ValidationError("An assignment with that title already exists")

    def validate_files(form, field):
        """
        Validate that source filenames do not contain any invalid characters.
        """

        filenames = field.data.split()

        bad_names = []

        for f in filenames:
            if not re.fullmatch("(\w[\w-]*|\*)(\.[\w-]+)*", f):
                bad_names.append(f)

        if len(bad_names) != 0:
            raise ValidationError("The following filenames are invalid: " + ", ".join(bad_names))



@admin.route('/assignments', methods=['get', 'post'])
@login_required
def admin_assignments():
    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    new_assignment_form = NewAssignmentForm()

    if new_assignment_form.validate_on_submit():
        # create new assignment for DB
        new_base_assignment = BaseAssignment(title=new_assignment_form.title.data,
                                                        tester_run_command=new_assignment_form.tester_run_command.data,
                                                        max_runtime=new_assignment_form.max_runtime.data)

        db.session.add(new_base_assignment)
        db.session.commit()

        current_app.logger.info(f"Created new base assignment with ID {new_base_assignment.assignment_id}")

        # create separate SourceFile entries for each source file
        assignment_files = new_assignment_form.files.data.split()

        # TODO: check for duplicate filenames
        for af in assignment_files:
            new_file = SourceFile(filename=af,
                                  base_assignment_id=new_base_assignment.assignment_id)
            db.session.add(new_file)
            current_app.logger.info(f"Added source file {af} to base assignment")

        db.session.commit()

        # Create separate TesterFile entries for each uploaded tester
        # file and save files to a directory for workers to access.
        tester_files = request.files.getlist(new_assignment_form.tester_files.name)

        tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                        f"{new_base_assignment.assignment_id}")
        os.makedirs(tester_code_dir, exist_ok=True)
        current_app.logger.debug(f"Set assignment tester code dir: {tester_code_dir}")

        for tf in tester_files:
            # TODO: store tf.content_type attribute in DB
            new_tester_file = TesterFile(filename=tf.filename,
                                         data=tf.read(),
                                         base_assignment=new_base_assignment)
            db.session.add(new_tester_file)

            new_tester_file.write_to_file(current_app.config['TESTER_CODE_BASE_DIR'])

            current_app.logger.info(f"Added tester file {tf.filename} to base assignment")

        db.session.commit()

        flash(f"Assignment named '{new_assignment_form.title.data}' added with {len(assignment_files)} assignment files and {len(tester_files)} tester files!", "info")

        return redirect(url_for(f'.admin_assignments'))


    all_assignments = BaseAssignment.query

    return render_template("admin_assignments.html",
                            page_title="Admin Assignments",
                            assignment_form=new_assignment_form,
                            assignments=all_assignments)


@admin.route("/gitolite/assignment/<int:assignment_id>")
@login_required
def get_gitolite_conf(assignment_id):

    if not current_user.admin:
        current_app.logger.warning(f"Unauthorized admin access attempt: {current_user.username}")
        abort(403)

    assignment = (
        Assignment.query
            .filter(Assignment.assignment_id == assignment_id)
            .first()
    )

    if not assignment:
        abort(404)
        current_app.logger.error(f"No assignment found with id {assignment_id}")

    section = assignment.section

    response = ""

    for group in assignment.teams:
        repo_name = f"{section.course}-{section.semester}-s{section.section_num:02}-psa{assignment.num}-group{group.team_num}"
        response += f"repo {repo_name}\n"

        # set up git hook to send notification to SAFE app
        response += "\toption hook.post-receive = notify-safe\n"

        # add read/write permissions to course staff (i.e. instructors)
        response += f"\tRW+ = @{section.course}-{section.semester}-s{section.section_num:02}-staff\n"

        # add read/write permissions to group members
        group_usernames = " ".join([member.username for member in group.members])
        response += f"\tRW+ = {group_usernames}\n"

        # give read-only permission to the safe_app
        response += f"\tR   = safe_app\n\n"


    return response, 200, {'Content-Type': 'text/plain'}

