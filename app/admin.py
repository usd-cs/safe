import os
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
from sqlalchemy import insert, delete, and_
from werkzeug.utils import secure_filename
from . import db_models

from app.helper import get_formatted_file_contents

admin = Blueprint('admin', __name__)


def check_instructor_username(form, field):
    with current_app.Session() as session:
        if session.query(db_models.User).filter(db_models.User.username == field.data).count() != 0:
            raise ValidationError("An instructor with that username already exists")


class NewInstructorForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    username = StringField('USD Username', validators=[DataRequired(), check_instructor_username])
    admin = BooleanField('Admin')
    submit = SubmitField('Submit')


@admin.route('/')
@login_required
def admin_home():
    if not current_user.admin:
        abort(403)
        
    return render_template("admin.html", 
            page_title="Admin Home: SAFE @ USD",
            user=current_user)


@admin.route('/users')
@login_required
def admin_users():
    if not current_user.admin:
        abort(403)

    with current_app.Session() as session:
        all_users = session.query(db_models.User).order_by(db_models.User.last_name).all()

        return render_template("admin_users.html", 
                                page_title="Admin Users: SAFE @ USD", 
                                user=current_user,
                                users=all_users)
        

@admin.route('/instructors', methods=['get', 'post'])
@login_required
def admin_instructors():
    if not current_user.admin:
        abort(403)
        
    form = NewInstructorForm()

    if form.validate_on_submit():
        # add user to database
        with current_app.Session() as session:
            new_instructor = db_models.User(username=form.username.data,
                                                first_name=form.first_name.data,
                                                last_name=form.last_name.data,
                                                admin=form.admin.data,
                                                instructor=True)
            session.add(new_instructor)
            session.commit()

            flash(f"Added new instructor: {new_instructor.first_name} {new_instructor.last_name}", "success")

        return redirect(url_for('.admin_instructors'))

    # form wasn't valid so re-render the page
    with current_app.Session() as session:
        instructors = (
            session.query(db_models.User)
                .filter(db_models.User.instructor == True)
                .order_by(db_models.User.last_name)
        )

        return render_template("admin_instructors.html", 
                                page_title="Admin Instructors: SAFE @ USD", 
                                user=current_user,
                                form=form,
                                instructors=instructors) 


# TODO: This is a generic form element so don't bury this in here
class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class NewSectionForm(FlaskForm):
    course = SelectField('Course', 
                            choices=[('comp110', 'COMP110: Computational Problem Solving')])
    semester = SelectField('Semester', 
                            choices=[('sp21', 'Spring 2021'),
                                     ('fa21', 'Fall 2021')])
    #semester = StringField('Semester', validators=[AnyOf(['sp21', 'fa21'])])
    section_num = IntegerField('Section Number', validators=[NumberRange(min=1)])
    instructors = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")

class ModifySectionForm(FlaskForm):
    instructors = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")


@admin.route('/sections/modify', methods=['get', 'post'])
@login_required
def modify_section():
    if not current_user.admin:
        abort(403)

    section_id = request.args.get('section_id')

    if not section_id:
        abort(404)
    else:
        try:
            section_id = int(section_id)
        except ValueError:
            flash(f"Invalid value for section_id: {section_id}", "danger")
            return redirect(url_for('.admin_sections'))

    with current_app.Session() as session:
        # verify there is a section with the given ID
        section = (
            session.query(db_models.Section)
                .filter(db_models.Section.section_id == section_id)
                .first()
            )

        if not section:
            abort(404)

        all_instructors = (
            session.query(db_models.User)
                .filter(db_models.User.instructor == True)
        )

        section_instructors = [user for user in section.users if user.instructor == True]

    form = ModifySectionForm()

    id_list = [i.user_id for i in all_instructors]
    name_list = [f"{i.last_name}, {i.first_name} ({i.username})" for i in all_instructors]

    form.instructors.choices = zip(id_list, name_list)
    previous_instructors_ids = [i.user_id for i in section_instructors]

    if form.validate_on_submit():
        print("\n\n\nMOOOO selected:", form.instructors.data)
        with current_app.Session() as session:
            # add newly selected instructors to section
            for instructor_id in form.instructors.data:
                if instructor_id not in previous_instructors_ids:
                    statement = (
                        insert(db_models.section_enrollment)
                            .values(user_id=instructor_id, section_id=section_id)
                    )
                    session.execute(statement)

            # remove old instructors who weren't selected this time
            for instructor_id in previous_instructors_ids:
                if instructor_id not in form.instructors.data:
                    statement = (
                        delete(db_models.section_enrollment)
                            .where(db_models.section_enrollment.c.user_id == instructor_id,
                                db_models.section_enrollment.c.section_id == section_id)
                    )
                    session.execute(statement)

            session.commit()

            return redirect(url_for('.modify_section', section_id=section_id))

    # pre-fill old instructors into selections
    form.instructors.data = previous_instructors_ids[:]

    return render_template("modify_section.html",
                            page_title="Modify Section: SAFE @ USD",
                            user=current_user,
                            section=section,
                            form=form)


@admin.route('/sections', methods=['get', 'post'])
@login_required
def admin_sections():
    if not current_user.admin:
        abort(403)
        
    form = NewSectionForm()

    with current_app.Session() as session:
        all_instructors = (
            session.query(db_models.User)
                .filter(db_models.User.instructor == True)
        )

        all_sections = (
            session.query(db_models.Section)
                .order_by(db_models.Section.course, db_models.Section.semester, db_models.Section.section_num)
        )

        # create a list of (section, instructors) tuples
        section_info = []

        for section in all_sections:
            section_instructors = (
                session.query(db_models.User)
                    .join(db_models.section_enrollment)
                    .join(db_models.Section)
                    .filter(and_(db_models.Section.section_id == section.section_id, 
                                    db_models.User.instructor == True))
                    .order_by(db_models.User.last_name)
                    .all()
            )
            num_students = (
                session.query(db_models.User)
                    .join(db_models.section_enrollment)
                    .join(db_models.Section)
                    .filter(and_(db_models.Section.section_id == section.section_id, 
                                    db_models.User.instructor == False))
                    .count()
            )
            print(f"section {section.section_id}: {len(section_instructors)} instructors, {num_students} students")
            section_info.append((section, section_instructors, num_students))

    id_list = [i.user_id for i in all_instructors]
    name_list = [f"{i.last_name}, {i.first_name} ({i.username})" for i in all_instructors]

    form.instructors.choices = zip(id_list, name_list)

    if form.validate_on_submit():
        with current_app.Session() as session:
            # TODO: Turn this isn't a form validator so error shows up closer to
            # where it matters (i.e. under the section field, not as a flash at
            # the top of the page.
            num_matching_sections = (
                session.query(db_models.Section)
                    .filter(db_models.Section.course == form.course.data)
                    .filter(db_models.Section.semester == form.semester.data)
                    .filter(db_models.Section.section_num == int(form.section_num.data))
                    .count()
            )

            # make sure a section with given info doesn't already exist
            if num_matching_sections != 0:
                flash("A section with that information already exists!", "danger")
                form.instructors.choices = zip(id_list, name_list)

                return render_template("admin_sections.html",
                                        page_title="Admin Sections: SAFE @ USD",
                                        user=current_user,
                                        form=form,
                                        sections=section_info)

            # create the new section and add it to the database
            new_section = db_models.Section(course=form.course.data,
                                            semester=form.semester.data,
                                            section_num=int(form.section_num.data))


            session.add(new_section)
            session.flush() # causes DB to give the new_section a section_id

            # add instructors to section
            for instructor_id in form.instructors.data:
                statement = (
                    insert(db_models.section_enrollment)
                        .values(user_id=instructor_id, section_id=new_section.section_id)
                )
                session.execute(statement)

            session.commit()

            flash(f"Succesfully added new section: {new_section.course.upper()}, Section {new_section.section_num} ({new_section.semester.upper()})", "success")

        return redirect(url_for('.admin_sections'))

    print("form errors:", form.errors)

    form.instructors.choices = zip(id_list, name_list)

    return render_template("admin_sections.html",
                            page_title="Admin Sections: SAFE @ USD",
                            user=current_user,
                            form=form,
                            sections=section_info)


def get_tester_file(assignment_id, filename, session):
    return (
        session.query(db_models.TesterFile)
            .join(db_models.BaseAssignment.tester_files)
            .filter(db_models.BaseAssignment.assignment_id == assignment_id)
            .filter(db_models.TesterFile.filename == filename)
            .first()
    )


class AddTesterFilesForm(FlaskForm):
    new_files = MultipleFileField('New Tester Files', validators=[DataRequired()])
    submit = SubmitField("Submit")


@admin.route("/assignments/<int:assignment_id>/tester_files/add", methods=['get','post'])
@login_required
def add_tester_files(assignment_id):
    if not current_user.admin:
        abort(403)

    with current_app.Session() as session:
        assignment = (
            session.query(db_models.BaseAssignment)
                .filter(db_models.BaseAssignment.assignment_id == assignment_id)
                .first()
        )

        if not assignment:
            abort(404)

        add_files_form = AddTesterFilesForm()

        if add_files_form.validate_on_submit():
            # Create separate TesterFile entries for each uploaded tester
            # file and save files to a directory for workers to access.
            new_files = request.files.getlist(add_files_form.new_files.name)

            tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                            f"{assignment.assignment_id}")

            existing_tester_files = [tf.filename for tf in assignment.tester_files]

            skipped_files = []
            for tf in new_files:
                if tf.filename in existing_tester_files:
                    # if there is already a file with this name, skip it
                    skipped_files.append(tf.filename)
                    continue

                # TODO: store tf.content_type attribute in DB
                new_tester_file = db_models.TesterFile(filename=tf.filename,
                                                        data=tf.read(),
                                                        base_assignment_id=assignment.assignment_id)
                session.add(new_tester_file)

                # save to the tester code directory
                filename = secure_filename(tf.filename)
                file_location = os.path.join(tester_code_dir, filename)
                with open(file_location, 'wb') as new_file:
                    new_file.write(new_tester_file.data)

            session.commit()

            if len(skipped_files) > 0:
                flash(f"The following files already exist and were skipped: {' '.join(skipped_files)}",
                        "warning")

            if len(new_files) > len(skipped_files):
                flash(f"Added {len(new_files) - len(skipped_files)} files to assignment '{assignment.title}'",
                        "success")

            return redirect(url_for('.admin_assignments'))


        return render_template("admin_add_tester_files.html",
                                user=current_user,
                                assignment=assignment,
                                files_form=add_files_form)

@admin.route("/assignments/<int:assignment_id>/tester_files/<filename>/delete")
@login_required
def delete_tester_file(assignment_id, filename):
    if not current_user.admin:
        abort(403)

    with current_app.Session() as session:
        tester_file = get_tester_file(assignment_id, filename, session)

        if not tester_file:
            abort(404)

        # remove the file from the tester code directory
        tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                        f"{assignment_id}")

        tester_file_loc = os.path.join(tester_code_dir, filename)
        os.remove(tester_file_loc)

        # delete from our database
        session.delete(tester_file)
        session.commit()

        return redirect(url_for('.admin_assignments'))


class UpdateTesterFileForm(FlaskForm):
    tester_file = FileField('Replacement File', validators=[FileRequired()])
    submit = SubmitField('Replace File')


@admin.route("/assignments/<int:assignment_id>/tester_files/<filename>", methods=['get', 'post'])
@login_required
def view_tester_file(assignment_id, filename):
    if not current_user.admin:
        abort(403)

    with current_app.Session() as session:
        tester_file = get_tester_file(assignment_id, filename, session)

        if not tester_file:
            abort(404)

        update_file_form = UpdateTesterFileForm()

        if update_file_form.validate_on_submit():
            # add users to database
            uploaded_file = update_file_form.tester_file.data
            sec_filename = secure_filename(uploaded_file.filename)

            if sec_filename == filename:
                # update file contents in database
                tester_file.data = uploaded_file.read()
                session.commit()

                # save uploaded file to tester code directory
                tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                                f"{assignment_id}")
                file_location = os.path.join(tester_code_dir, sec_filename)

                with open(file_location, 'wb+') as new_file:
                    new_file.write(tester_file.data)

                flash("File has been updated!", "success")
            else:
                flash(f"Uploaded filename ({sec_filename}) differs from this file.", "danger")


        formatted_file = get_formatted_file_contents(tester_file)

        # TODO: send md5sum and creation date to template

        return render_template("file_viewer.html", 
                                user=current_user,
                                filename=tester_file.filename,
                                file_contents=formatted_file,
                                update_file_form=update_file_form)

@admin.route("/users/delete")
@login_required
def admin_delete_user():
    if not current_user.admin:
        abort(403)
        
    user_id = request.args.get('id')

    # if user id wasn't specified, just redirect to admin page for users
    if not user_id:
        flash("Could not delete user. ID missing.", "danger")
    else:
        with current_app.Session() as session:
            user = session.query(db_models.User).filter(db_models.User.user_id == int(user_id)).first()

            if not user:
                flash("Could not delete user. Invalid ID.", "danger")
            else:
                flash(f"Successfully deleted user {user.username}", "success")
                session.delete(user)
                session.commit()

    return redirect(url_for('.admin_users'))


class NewAssignmentForm(FlaskForm):
    # TODO: add validator that title is unique
    title = StringField('Assignment Title', validators=[DataRequired()])
    tester_run_command = StringField('Tester Run Command', validators=[DataRequired()])
    # TODO: add validator for formated of files field
    files = StringField('Assignment Files', validators=[DataRequired()])
    tester_files = MultipleFileField('Tester Files', validators=[DataRequired()])
    max_runtime = IntegerField('Maximum Test Runtime', validators=[NumberRange(min=1)])
    submit = SubmitField("Submit")


@admin.route('/assignments', methods=['get', 'post'])
@login_required
def admin_assignments():
    if not current_user.admin:
        abort(403)
        
    new_assignment_form = NewAssignmentForm()

    if new_assignment_form.validate_on_submit():
        with current_app.Session() as session:
            # create new assignment for DB
            new_base_assignment = db_models.BaseAssignment(title=new_assignment_form.title.data,
                                                            tester_run_command=new_assignment_form.tester_run_command.data,
                                                            max_runtime=new_assignment_form.max_runtime.data)

            session.add(new_base_assignment)
            session.flush()

            # create separate SourceFile entries for each source file
            assignment_files = new_assignment_form.files.data.split()
            
            # TODO: check for duplicate filenames
            for af in assignment_files:
                new_file = db_models.SourceFile(filename=af,
                                                base_assignment_id=new_base_assignment.assignment_id)
                session.add(new_file)

            session.flush()

            # Create separate TesterFile entries for each uploaded tester
            # file and save files to a directory for workers to access.
            tester_files = request.files.getlist(new_assignment_form.tester_files.name)

            tester_code_dir = os.path.join(current_app.config['TESTER_CODE_BASE_DIR'],
                                            f"{new_base_assignment.assignment_id}")
            os.makedirs(tester_code_dir, exist_ok=True)

            for tf in tester_files:
                # TODO: store tf.content_type attribute in DB
                new_tester_file = db_models.TesterFile(filename=tf.filename,
                                                        data=tf.read(),
                                                        base_assignment_id=new_base_assignment.assignment_id)
                session.add(new_tester_file)

                # save to the tester code directory
                filename = secure_filename(tf.filename)
                file_location = os.path.join(tester_code_dir, filename)
                with open(file_location, 'wb') as new_file:
                    new_file.write(new_tester_file.data)

            session.commit()

        flash(f"Assignment named '{new_assignment_form.title.data}' added with {len(assignment_files)} assignment files and {len(tester_files)} tester files!", "info")

        return redirect(url_for(f'.admin_assignments'))

    with current_app.Session() as session:
        all_assignments = session.query(db_models.BaseAssignment)

        return render_template("admin_assignments.html",
                                page_title="Admin Assignments: SAFE @ USD",
                                user=current_user,
                                assignment_form=new_assignment_form,
                                assignments=all_assignments)

