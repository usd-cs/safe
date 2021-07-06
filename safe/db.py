import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from sqlalchemy import create_engine, inspect


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
                        CREATE TABLE assignment (
                          assignment_id INTEGER NOT NULL PRIMARY KEY,
                          num INTEGER NOT NULL,
                          title VARCHAR NOT NULL,
                          section_id INTEGER REFERENCES section
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
                        CREATE TABLE source_file (
                          source_file_id INTEGER NOT NULL PRIMARY KEY,
                          filename VARCHAR NOT NULL,
                          assignment_id INTEGER REFERENCES psa
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
