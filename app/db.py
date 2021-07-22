import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import secrets
from werkzeug.security import generate_password_hash


def init_db(app):
    engine = create_engine(app.config['DATABASE_URI'],
                            echo=app.config['DATABASE_VERBOSE'])

    # if database is empty (i.e. hasn't been initialized), initialize it by
    # creating the basic tables.
    if inspect(engine).get_table_names() == []:
        print("Initializing database!")

        # FIXME: use "with engine.connect() as connection" here for executing
        engine.execute("""
                        CREATE TABLE user (
                          user_id INTEGER NOT NULL PRIMARY KEY,
                          admin BOOLEAN NOT NULL,
                          instructor BOOLEAN NOT NULL,
                          username VARCHAR NOT NULL UNIQUE,
                          password VARCHAR NOT NULL,
                          first_name VARCHAR NOT NULL,
                          last_name VARCHAR NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE section (
                          section_id INTEGER NOT NULL PRIMARY KEY,
                          course VARCHAR NOT NULL,
                          semester VARCHAR NOT NULL,
                          section_num INTEGER NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE base_assignment (
                          assignment_id INTEGER NOT NULL PRIMARY KEY,
                          title VARCHAR NOT NULL,
                          tester_run_command VARCHAR NOT NULL,
                          max_runtime INTEGER NOT NULL
                        )
                        """)
        engine.execute("""
                        CREATE TABLE assignment (
                          assignment_id INTEGER NOT NULL PRIMARY KEY,
                          num INTEGER NOT NULL,
                          section_id INTEGER REFERENCES section,
                          base_assignment_id INTEGER REFERENCES base_assignment
                        )
                        """)
        engine.execute("""
                        CREATE TABLE team (
                          team_id INTEGER NOT NULL PRIMARY KEY,
                          team_num INTEGER NOT NULL,
                          assignment_id INTEGER REFERENCES assignment
                        )
                        """)
        engine.execute("""
                        CREATE TABLE test_results (
                          job_id VARCHAR NOT NULL PRIMARY KEY,
                          finished BOOLEAN NOT NULL,
                          results VARCHAR,
                          commit_time DATETIME,
                          commit_author VARCHAR,
                          commit_comment VARCHAR,
                          completed_at DATETIME,
                          team_id INTEGER REFERENCES team
                        )
                        """)
        engine.execute("""
                        CREATE TABLE source_file (
                          source_file_id INTEGER NOT NULL PRIMARY KEY,
                          filename VARCHAR NOT NULL,
                          base_assignment_id INTEGER REFERENCES base_assignment
                        )
                        """)
        engine.execute("""
                        CREATE TABLE tester_file (
                          id INTEGER NOT NULL PRIMARY KEY,
                          filename VARCHAR NOT NULL,
                          data BLOB NOT NULL,
                          base_assignment_id INTEGER REFERENCES base_assignment
                        )
                        """)
        engine.execute("""
                        CREATE TABLE team_enrollment (
                          user_id INTEGER REFERENCES student,
                          team_id INTEGER REFERENCES team
                        )
                        """)
        engine.execute("""
                        CREATE TABLE section_enrollment (
                          user_id INTEGER REFERENCES student,
                          section_id INTEGER REFERENCES section
                        )
                        """)

        engine.execute("""
                        CREATE TABLE password_reset_request (
                          request_id INTEGER NOT NULL PRIMARY KEY,
                          hashed_id VARCHAR NOT NULL,
                          time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                          user_id INTEGER REFERENCES user
                        )
                        """)

    from . import db_models
    db_models.Base.metadata.create_all(engine)

    # if no users yet (i.e. first run), create our first admin user
    Session = sessionmaker(engine)
    with Session() as session:
        if session.query(db_models.User).count() == 0:
            print(f"Creating first user: {app.config['FIRST_ADMIN_USER']}")

            import string
            alphabet = string.ascii_letters + string.digits
            temporary_password = ''.join(secrets.choice(alphabet) for i in range(20))

            admin_user = db_models.User(username=app.config['FIRST_ADMIN_USER'][0],
                                        password=generate_password_hash(temporary_password),
                                        first_name=app.config['FIRST_ADMIN_USER'][1],
                                        last_name=app.config['FIRST_ADMIN_USER'][2],
                                        admin=True,
                                        instructor=True)
            session.add(admin_user)
            session.commit()

    return engine


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
