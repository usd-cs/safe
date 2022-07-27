from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from flask_login import current_user, login_user, logout_user, LoginManager

from cas import CASClient
from unittest.mock import Mock

from . import db_models
from app import db

auth = Blueprint('auth', __name__)

login_manager = LoginManager()


def init_auth(app):
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = None


    with app.app_context():
        if app.config.get("MOCK_CAS") == True:
            server_url = url_for('cas.mock_cas_home')
        else:
            assert app.config.get('CAS_SERVER_URL') is not None, "CAS_SERVER_URL not set in config"
            server_url = app.config.get('CAS_SERVER_URL')

        app.cas_client = CASClient(
            version=3,
            service_url=url_for('auth.verify_ticket', next=url_for('user_views.root', _external=False)),
            server_url=server_url
        )

        if app.config.get("MOCK_CAS") == True:
            from app.cas import verify_mock_ticket
            app.cas_client.verify_ticket = Mock(side_effect=verify_mock_ticket)

    app.logger.debug(f'Initial CAS service_url: {app.cas_client.service_url}')


@login_manager.user_loader
def load_user(user_id):
    current_app.logger.debug(f"loading user: {user_id}")

    matching_users = (
        db_models.User.query.filter(db_models.User.user_id == int(user_id))
    )

    if matching_users.count() == 1:
        return matching_users.first()
    else:
        current_app.logger.error(f"Couldn't find user with id {user_id}")
        return None


@auth.route('/login', methods = ['POST', 'GET'])
def login():
    next_url = request.args.get('next')

    if current_user.is_authenticated:
        flash(f"You are already signed in as {current_user.username}", "warning")
        if next_url is None:
            return redirect(url_for('user_views.root'))
        else:
            return redirect(next_url)

    service_url = f"{url_for('.verify_ticket', _external=True)}"
    if next_url:
        service_url += f"?next={next_url}"

    current_app.cas_client.service_url = service_url
    current_app.logger.debug(f"login: CAS service_url: {current_app.cas_client.service_url}")

    cas_login_url = current_app.cas_client.get_login_url()
    return redirect(cas_login_url)


@auth.route('/verify_ticket')
def verify_ticket():
    next_url = request.args.get('next')
    ticket = request.args.get('ticket')

    if not ticket:
        # If there isn't a ticket, flash a message and send them to home page
        current_app.logger.error("Missing ticket for verify_ticket")
        flash("Login process failed: missing authentication ticket!", "danger")
        return redirect(url_for('user_views.root'))

    # validate ticket and get username by calling verify_ticket
    username, attributes, pgtiou = current_app.cas_client.verify_ticket(ticket)

    current_app.logger.debug(f'CAS verify_ticket response: username: {username}, attributes: {attributes}, pgtiou: {pgtiou}')

    if not username:
        # verifying ticket failed so send them to the homepage
        current_app.logger.warning("Authentication failed")
        flash("Login process failed: authentication failed!", "danger")
        return redirect(url_for('user_views.root'))

    username = username.lower()

    # try to find the username in our database
    matching_user = db_models.User.query.filter(db_models.User.username == username).first()

    if not matching_user:
        # couldn't find this user in our database
        current_app.logger.warning(f"Unauthorized login attempt: {username}")
        flash("Login process failed: unauthorized user!", "danger")
        return redirect(url_for('user_views.root'))
    else:
        # login process complete!
        login_user(matching_user)
        current_app.logger.info(f"Successful login: {username}")
        flash(f"You have successfully signed in as {username}!", "success")
        if next_url is None:
            return redirect(url_for('user_views.root'))
        else:
            return redirect(next_url)


@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        current_app.logger.info(f"logout: {current_user.username}")
        logout_user()
        flash("You've successfully logged out!", "success")

        redirect_url = url_for('user_views.root', _external=True)
        cas_logout_url = current_app.cas_client.get_logout_url(redirect_url)
        current_app.logger.debug(f'CAS logout URL: {cas_logout_url}')

        return redirect(cas_logout_url)
    else:
        flash("You must be signed in before you can log out!", "warning")
        return redirect(url_for('user_views.root'))
