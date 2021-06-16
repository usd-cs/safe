import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from sqlalchemy import create_engine, inspect


def get_db():
    if 'db_engine' not in g:
        g.db_engine = create_engine(app.config['DATABASE_URI'],
                                    echo=app.config['DATABASE_VERBOSE'])

    return g.db_engine


def init_db(app):
    engine = create_engine(app.config['DATABASE_URI'], echo=True)

    # if database is empty (i.e. hasn't been initialized), initialize it by
    # creating the basic tables.
    if inspect(engine).get_table_names() == []:
        print("Initializing database!")

        # FIXME: use "with engine.connect() as connection" here for executing
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

    from . import db_models
    db_models.Base.metadata.create_all(engine)
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
