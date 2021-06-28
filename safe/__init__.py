import os
import json
from collections import namedtuple

from flask import Flask, render_template, redirect, url_for, abort, request
from sqlalchemy import create_engine, inspect, insert, and_
from sqlalchemy.orm import sessionmaker
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField, SelectMultipleField, IntegerField
from flask_wtf.file import FileField, FileRequired
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.validators import ValidationError, DataRequired, Length, AnyOf, Regexp, NumberRange
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        #DATABASE=os.path.join(app.instance_path, 'safe.sqlite'),
        DATABASE_URI='sqlite:///safe.sqlite3',
        DATABASE_VERBOSE=True
    )

    # try to make the instance folder
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    from . import db_models
    db_engine = db.init_db(app)
    Session = sessionmaker(db_engine)

    def check_instructor_username(form, field):
        with Session() as session:
            if session.query(db_models.User).filter(db_models.User.username == field.data).count() != 0:
                raise ValidationError("An instructor with that username already exists")


    class NewInstructorForm(FlaskForm):
        first_name = StringField('First Name', validators=[DataRequired()])
        last_name = StringField('First Name', validators=[DataRequired()])
        username = StringField('USD Username', validators=[DataRequired(), check_instructor_username])
        password = PasswordField('Password', validators=[DataRequired(), Length(min=5, max=20)])
        submit = SubmitField('Submit')


    @app.route('/admin')
    def admin_home():
        return render_template("admin.html", page_title="Admin Home: SAFE @ USD")

    @app.route('/admin/instructors', methods=['get', 'post'])
    def admin_instructors():
        form = NewInstructorForm()

        if form.validate_on_submit():
            # add user to database
            with Session() as session:
                new_instructor = db_models.User(username=form.username.data,
                                                    password=generate_password_hash(form.password.data),
                                                    first_name=form.first_name.data,
                                                    last_name=form.last_name.data,
                                                    instructor=True,
                                                    admin=True)  # FIXME: limit who is admin
                session.add(new_instructor)
                session.commit()

                print("Number of instructor in DB:",
                        session.query(db_models.User).count())
            return redirect(url_for('admin_instructors'))

        # form wasn't valid so re-render the page
        with Session() as session:
            instructors = (
                session.query(db_models.User)
                    .filter(db_models.User.instructor == True)
                    .order_by(db_models.User.last_name)
            )

        return render_template("admin_instructors.html", 
                                page_title="Admin Instructors: SAFE @ USD", 
                                form=form,
                                instructors=instructors) 


    class MultiCheckboxField(SelectMultipleField):
        widget = ListWidget(prefix_label=False)
        option_widget = CheckboxInput()


    class NewSectionForm(FlaskForm):
        # TODO: use regex for course, semester, and section_num
        course = StringField('Course', validators=[AnyOf(['comp110'])])
        semester = StringField('Semester', validators=[AnyOf(['sp21', 'fa21'])])
        section_num = StringField('Section Number', validators=[DataRequired()])
        instructors = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
        submit = SubmitField("Submit")


    @app.route('/admin/sections', methods=['get', 'post'])
    def admin_sections():
        form = NewSectionForm()

        with Session() as session:
            #instructors = session.query(db_models.User).order_by(db_models.User.last_name).all()
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
            with Session() as session:
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


                print("Number of Sections in DB:",
                        session.query(db_models.Section).count())

            return redirect(url_for('admin_sections'))

        print("form errors:", form.errors)

        # NOTE: I'm not sure why validating resets the instructor choices but
        # we need to reset them in case validation fails
        form.instructors.choices = zip(id_list, name_list)

        return render_template("admin_sections.html",
                                page_title="Admin Sections: SAFE @ USD",
                                form=form,
                                sections=section_info)

    @app.route('/profile/<username>')
    def user_profile(username):
        with Session() as session:
            selected_user = (
                session.query(db_models.User)
                    .filter(db_models.User.username == username)
                    .first()
            )


        if selected_user:
            # if user exists, grab the list of classes they are enrolled in and
            # render the profile page view
            with Session() as session:
                enrolled_courses = (
                    session.query(db_models.Section)
                        .join(db_models.section_enrollment)
                        .join(db_models.User)
                        .filter(db_models.User.username == selected_user.username)
                        .all()
                )

            return render_template("user_profile.html",
                                    page_title=f"User Profile ({selected_user.username}) : SAFE @ USD",
                                    user=selected_user,
                                    courses=enrolled_courses)
        else:
            # the user doesn't exist so 404 'em
            abort(404)

    @app.route('/')
    def root():
        return render_template("main.html", page_title="Home: SAFE @ USD")


    class NewAssignmentForm(FlaskForm):
        assignment_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
        title = StringField('Assignment Title', validators=[DataRequired()])
        submit = SubmitField("Submit")

    class RosterUploadForm(FlaskForm):
        roster_file = FileField('Class Roster', validators=[FileRequired()])
                #validators=[Regexp('^.*\.(csv|CSV)$', message="Must be CSV file format")])
        submit = SubmitField('Upload Roster')

    # TODO: generalize for non-COMP110 courses
    @app.route('/comp110/<semester>/s<int:section_num>/', methods=['get', 'post'])
    def section_overview(semester, section_num):
        # TODO: check that section actually exists, displaying 404 if not

        new_assignment_form = NewAssignmentForm()
        roster_upload_form = RosterUploadForm()

        if new_assignment_form.validate_on_submit():
            with Session() as session:
                section = (
                    session.query(db_models.Section)
                        .filter(db_models.Section.course == "comp110")
                        .filter(db_models.Section.semester == semester)
                        .filter(db_models.Section.section_num == section_num)
                        .first()
                )

                num_matches = (
                        session.query(db_models.Assignment)
                            .filter(db_models.Assignment.section_id == section.section_id)
                            .filter(db_models.Assignment.num == new_assignment_form.assignment_num.data)
                            .count()
                )

                if num_matches != 0:
                    print("ERROR: assignment already exists!")
                    # TODO: flash error with this message to alert user of the
                    # issue

                else:
                    print("SUCCESS: Adding new assignment!")
                    new_assignment = db_models.Assignment(num=new_assignment_form.assignment_num.data,
                                                            title=new_assignment_form.title.data,
                                                            section_id=section.section_id)

                    session.add(new_assignment)
                    session.commit()

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

            with open(file_location, 'r') as roster_data:
                header = roster_data.readline()

                with Session() as session:
                    for line in roster_data:
                        columns = line.strip().split(',')

                        # FIXME: validate format of CSV file
                        print(columns[2], columns[3], columns[-1])
                        username = columns[-1].split("@")[0]
                        last_name = columns[2]
                        first_name = columns[3]

                        # check that student with that username doesn't exist
                        if session.query(db_models.User).filter(db_models.User.username == username).count() > 0:
                            # found the student already so skip it
                            print(f"User with {username} already exists. Skipping creation!")
                        else:
                            # Create new User and add to database
                            print(f"Adding student with username {username}")
                            new_student = db_models.User(username=username,
                                                            password=generate_password_hash("FIXME"),
                                                            first_name=first_name,
                                                            last_name=last_name,
                                                            instructor=False,
                                                            admin=False)
                            session.add(new_student)
                            session.flush()

                            # Add user to this section
                            section = (
                                # FIXME: filter on course and semester too!!!
                                session.query(db_models.Section)
                                    .filter(db_models.Section.section_id == section_num)
                                    .first()
                            )

                            # FIXME: confirm this section actually exists!
                            statement = (
                                insert(db_models.section_enrollment)
                                    .values(user_id=new_student.user_id, section_id=section.section_id)
                            )
                            session.execute(statement)

                            session.commit()

            os.remove(file_location)

            return redirect(url_for(f'section_overview', semester=semester, section_num=section_num))

        with Session() as session:
            section = (
                # FIXME: filter on course and semester too!!!
                session.query(db_models.Section)
                    .filter(db_models.Section.section_num == section_num)
                    .first()
            )

            enrolled_users = (
                session.query(db_models.User)
                    .join(db_models.section_enrollment)
                    .join(db_models.Section)
                    # TODO: also filter for correct course
                    .filter(and_(db_models.Section.section_id == section_num,
                                    db_models.Section.semester == semester,
                                    db_models.Section.course == "comp110"))
                    .all()
            )

            return render_template("section_overview.html", 
                                    page_title="Section Overview: SAFE @ USD",
                                    section=section,
                                    users=enrolled_users,
                                    assignment_form=new_assignment_form,
                                    roster_form=roster_upload_form
                                    )

    class NewGroupForm(FlaskForm):
        group_num = IntegerField('Assignment Number', validators=[NumberRange(min=0)])
        members = MultiCheckboxField('Instructors', coerce=int, validators=[DataRequired()])
        submit = SubmitField("Submit")

    # TODO: generalize for non comp110-courses
    @app.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/", methods=['get', 'post'])
    def psa_overview(semester, section_num, psa_num):
        new_group_form = NewGroupForm()

        with Session() as session:
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
                                    section=section,
                                    assignment=assignment,
                                    teams=assignment.teams,
                                    group_form=new_group_form)


    TestResult = namedtuple('TestResult', ['status', 'summary', 'detail'])

    @app.route("/comp110/<semester>/s<int:section_num>/psa<int:psa_num>/group<int:group_num>/")
    def psa_results(semester, section_num, psa_num, group_num):
        # TODO: validate semester, section num, psa_num, and group_num

        with Session() as session:
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
            
            # Read results from JSON file, filling them in a dictionary that is
            # organized by section.

            results = {}
            # FIXME: results file should depend on configured results directory
            # and course/semester/section/psa/group.
            with open('safe/mock_results.json', 'r') as results_file:

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
                                    assignment=assignment,
                                    group_num=group_num,
                                    submit_time=json_results["submission_time"],
                                    commit_comment=json_results["commit_comment"],
                                    results_time=json_results["results_time"],
                                    test_results=results)

    @app.route('/assignments/add/')
    def add_assignment():
        with Session() as session:
            #assignment_title = f"Cool assignment {next_assignment_num}"
            new_psa = db_models.PSA( title="Farts")
            session.add(new_psa)
            session.commit()
            #next_assignment_num += 1
            return f"Successfully added assignment {new_psa.psa_id}"


    @app.route('/assignments/')
    def get_assignments():
        with Session() as session:
            print(f"found: {session.query(db_models.PSA).count()}")
            html_str = ""
            for psa in session.query(db_models.PSA).all():
                print(psa)
                html_str += psa.title + "<br/>"

            return html_str

    return app
