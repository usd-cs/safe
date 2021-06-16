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
    )

    # try to make the instance folder
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    #from . import db
    #db.init_app(app)

    engine = create_engine(app.config['DATABASE_URI'], echo=True)

    # if database is empty (i.e. hasn't been initialized), initialize it by
    # creating the basic tables.
    if inspect(engine).get_table_names() == []:
        print("Initializing database!")
        engine.execute("""
                        CREATE TABLE instructor (
                          instructor_id INTEGER NOT NULL PRIMARY KEY,
                          username VARCHAR NOT NULL UNIQUE,
                          password VARCHAR NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE section (
                          section_id INTEGER NOT NULL PRIMARY KEY,
                          instructor_id INTEGER REFERENCES instructor
                        )
                        """)
        engine.execute("""
                        CREATE TABLE student (
                          student_id INTEGER NOT NULL PRIMARY KEY,
                          username VARCHAR NOT NULL UNIQUE,
                          password VARCHAR NOT NULL,
                          section_id INTEGER REFERENCES section
                        )
                        """)
        engine.execute("""
                        CREATE TABLE psa (
                          psa_id INTEGER NOT NULL PRIMARY KEY,
                          title VARCHAR NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE team (
                          team_id INTEGER NOT NULL PRIMARY KEY,
                          team_num INTEGER NOT NULL,
                          psa_id INTEGER REFERENCES psa,
                          section_id INTEGER REFERENCES section,
                          CONSTRAINT uc_teaminfo UNIQUE (team_num, psa_id, section_id)
                        )
                        """)
        engine.execute("""
                        CREATE TABLE source_file (
                          source_file_id INTEGER NOT NULL PRIMARY KEY,
                          psa_id INTEGER REFERENCES psa,
                          filename VARCHAR NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE student_team (
                          student_id INTEGER REFERENCES student,
                          team_id INTEGER REFERENCES team
                        )
                        """)
        print(inspect(engine).get_table_names())

    # create tables
    from . import db_models
    db_models.Base.metadata.create_all(engine)
    Session = sessionmaker(engine)

    @app.route('/')
    def root():
        return render_template("main.html")

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
