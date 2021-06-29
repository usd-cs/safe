import os
import json
from collections import namedtuple

from flask import Flask, render_template, redirect, url_for, abort, request
from sqlalchemy import create_engine, inspect, insert, and_, select
from sqlalchemy.orm import sessionmaker, with_parent
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField, SelectMultipleField, IntegerField, BooleanField
from flask_wtf.file import FileField, FileRequired
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.validators import ValidationError, DataRequired, Length, AnyOf, Regexp, NumberRange
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, current_user, login_user, logout_user, login_required

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        #DATABASE=os.path.join(app.instance_path, 'safe.sqlite'),
        DATABASE_URI='sqlite:///safe.sqlite3',
        DATABASE_VERBOSE=True
    )

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

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
        admin = BooleanField('Admin')
        submit = SubmitField('Submit')


    @login_manager.user_loader
    def load_user(user_id):
        print("loading user:", user_id)

        with Session() as session:
            matching_users = (
                session.query(db_models.User)
                    .filter(db_models.User.user_id == int(user_id))
            )

        if matching_users.count() == 1:
            return matching_users.first()
        else:
            print(f"Couldn't find user with id {user_id}")
            return None

    class LoginForm(FlaskForm):
        username = StringField(label=('Username'), validators=[DataRequired()])
        password = PasswordField(label=('Password'), validators=[DataRequired()])
        submit = SubmitField(label=('Submit'))

    @app.route('/login/', methods = ['POST', 'GET'])
    def login():
        if current_user.is_authenticated:
            next_url = request.args.get('next')
            if next_url is None:
                # TODO: flash message telling them they've already logged in
                return redirect(url_for('root'))
            else:
                print(next_url)
                return redirect(next_url)

        form = LoginForm()
        if form.validate_on_submit():
            with Session() as session:
                user_matches = (
                    session.query(db_models.User)
                        .filter(db_models.User.username == form.username.data)
                )

            if user_matches.count() == 1:
                matching_user = user_matches.first()
            else:
                matching_user = None

            if matching_user is None or not matching_user.check_password(form.password.data):
                # TODO: log invalid attempts
                flash("Invalid login credentials!")
            else:
                login_user(matching_user)
                next_url = request.args.get('next')
                if next_url is None:
                    # TODO: flash message telling them they've successfully logged in
                    return redirect(url_for('root'))
                else:
                    return redirect(next_url)

        return render_template('login.html', form=form)

    @app.route('/logout/')
    def logout():
        if current_user.is_authenticated:
            logout_user()
            # TODO: flash message telling them they've successfully logged out
        else:
            # TODO: flash message telling them they weren't logged in
            pass

        return redirect(url_for('root'))


    @app.route('/admin/')
    @login_required
    def admin_home():
        if not current_user.admin:
            abort(403)
            
        return render_template("admin.html", 
                page_title="Admin Home: SAFE @ USD",
                user=current_user)

    @app.route('/admin/instructors', methods=['get', 'post'])
    @login_required
    def admin_instructors():
        if not current_user.admin:
            abort(403)
            
        form = NewInstructorForm()

        if form.validate_on_submit():
            # add user to database
            with Session() as session:
                new_instructor = db_models.User(username=form.username.data,
                                                    password=generate_password_hash(form.password.data),
                                                    first_name=form.first_name.data,
                                                    last_name=form.last_name.data,
                                                    admin=form.admin.data,
                                                    instructor=True)
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
                                user=current_user,
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
    @login_required
    def admin_sections():
        if not current_user.admin:
            abort(403)
            
        form = NewSectionForm()

        with Session() as session:
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
                                user=current_user,
                                form=form,
                                sections=section_info)

    @app.route('/profile/<username>')
    @login_required
    def user_profile(username):
        if not (current_user.admin or current_user.instructor or
                current_user.username == username):
            abort(403)

        with Session() as session:
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
                                user=current_user)

    @app.errorhandler(403)
    def permission_denied(error):
        return render_template("forbidden.html",
                                user=current_user)

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
    @login_required
    def section_overview(semester, section_num):
        with Session() as session:
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
            with Session() as session:

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
                                        assignments=assignment_info
                                        )

        new_assignment_form = NewAssignmentForm()
        roster_upload_form = RosterUploadForm()

        if new_assignment_form.validate_on_submit():
            with Session() as session:
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
                                    user=current_user,
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
    @login_required
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
                                    user=current_user,
                                    assignment=assignment,
                                    group_num=group_num,
                                    submit_time=json_results["submission_time"],
                                    commit_comment=json_results["commit_comment"],
                                    results_time=json_results["results_time"],
                                    test_results=results)

    return app
