import sqlite3

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db_models import User, Base


def init_db(app):
    engine = create_engine(app.config['DATABASE_URI'],
                            echo=app.config['DATABASE_VERBOSE'])

    Base.metadata.create_all(engine)

    return engine


@click.command('add-admin')
@click.argument('username')
@click.argument('first_name')
@click.argument('last_name')
@with_appcontext
def add_admin_user(username, first_name, last_name):
    """Adds a new admin user to the database."""

    with current_app.Session() as session:
        admin_user = User(username=username,
                            first_name=first_name,
                            last_name=last_name,
                            admin=True,
                            instructor=True)
        session.add(admin_user)
        session.commit()

    click.echo(f"Added new admin user: {first_name} {last_name} ({username}).")



def init_app(app):
    app.cli.add_command(add_admin_user)
