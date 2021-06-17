import os

from flask import Flask, render_template
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

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
    db_engine = db.init_db(app)
    Session = sessionmaker(db_engine)

    @app.route('/admin')
    def admin_home():
        return render_template("admin.html", page_title="Admin Home: SAFE @ USD")

    @app.route('/admin/instructors')
    def admin_instructors():
        return render_template("admin_instructors.html", page_title="Admin Instructors: SAFE @ USD")

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
