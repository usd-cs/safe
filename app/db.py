import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import secrets


def init_db(app):
    engine = create_engine(app.config['DATABASE_URI'],
                            echo=app.config['DATABASE_VERBOSE'])

    from . import db_models
    db_models.Base.metadata.create_all(engine)

    # if no users yet (i.e. first run), create our first admin user
    Session = sessionmaker(engine)
    with Session() as session:
        if session.query(db_models.User).count() == 0:
            #print(f"Creating first user: {app.config['FIRST_ADMIN_USER']}")

            admin_user = db_models.User(username=app.config['FIRST_ADMIN_USER'][0],
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
