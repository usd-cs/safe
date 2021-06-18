import os

from flask import Flask, render_template, redirect, url_for
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField, SelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.validators import ValidationError, DataRequired, Length, AnyOf
from werkzeug.security import check_password_hash, generate_password_hash

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
            if session.query(db_models.Instructor).filter(db_models.Instructor.username == field.data).count() != 0:
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
                new_instructor = db_models.Instructor(username=form.username.data,
                                                        password=generate_password_hash(form.password.data),
                                                        first_name=form.first_name.data,
                                                        last_name=form.last_name.data)
                session.add(new_instructor)
                session.commit()

                print("Number of instructor in DB:",
                        session.query(db_models.Instructor).count())
            return redirect(url_for('admin_instructors'))

        # form wasn't valid so re-render the page
        with Session() as session:
            instructors = session.query(db_models.Instructor).order_by(db_models.Instructor.last_name)

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
            instructors = session.query(db_models.Instructor).order_by(db_models.Instructor.last_name).all()
            sections = session.query(db_models.Section, db_models.Instructor).join(db_models.Instructor, isouter=True).order_by(db_models.Section.course,
                                                                    db_models.Section.semester, 
                                                                    db_models.Section.section_num)

        id_list = [i.instructor_id for i in instructors]
        name_list = [f"{i.last_name}, {i.first_name} ({i.username})" for i in instructors]

        form.instructors.choices = zip(id_list, name_list)

        if form.validate_on_submit():
            with Session() as session:
                new_section = db_models.Section(course=form.course.data,
                                                semester=form.semester.data,
                                                section_num=int(form.section_num.data),
                                                instructor_id=form.instructors.data[0])
                session.add(new_section)
                session.commit()

                print("Number of Sections in DB:",
                        session.query(db_models.Section).count())
                pass

            return redirect(url_for('admin_sections'))

        print("form errors:", form.errors)

        # NOTE: I'm not sure why validating resets the instructor choices but
        # we need to reset them in case validation fails
        form.instructors.choices = zip(id_list, name_list)

        return render_template("admin_sections.html",
                                page_title="Admin Sections: SAFE @ USD",
                                form=form,
                                sections=sections)

    @app.route('/')
    def root():
        return render_template("main.html", page_title="Home: SAFE @ USD")

    #next_assignment_num = 12

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
