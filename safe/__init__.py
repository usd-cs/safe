import os

from flask import Flask, render_template, redirect, url_for
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField
from wtforms.validators import ValidationError, DataRequired, Length
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
            with Session() as session:
                print("Number of instructor in DB:",
                        session.query(db_models.Instructor).count())
                new_instructor = db_models.Instructor(username=form.username.data,
                                                        password=generate_password_hash(form.password.data))
                session.add(new_instructor)
                session.commit()
                return redirect(url_for('admin_instructors'))

        return render_template("admin_instructors.html", 
                                page_title="Admin Instructors: SAFE @ USD", 
                                form=form) 

    @app.route('/admin/sections')
    def admin_sections():
        return render_template("admin_sections.html", page_title="Admin Sections: SAFE @ USD")

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
