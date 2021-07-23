from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SubmitField, PasswordField
)
from wtforms.validators import DataRequired, InputRequired, Length, EqualTo
from werkzeug.security import generate_password_hash

# used for sending password recovery emails
import secrets, hashlib, smtplib, ssl, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from . import db_models

auth = Blueprint('auth', __name__)


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
    #print("CAS service_url:", current_app.cas_client.service_url)

    cas_login_url = current_app.cas_client.get_login_url()
    return redirect(cas_login_url)


@auth.route('/verify_ticket')
def verify_ticket():
    # TODO: log invalid attempts
    next_url = request.args.get('next')
    ticket = request.args.get('ticket')

    #print('ticket:', ticket)
    #print('next_url:', next_url)

    if not ticket:
        # If there isn't a ticket, flash a message and send them to home page
        flash("Login process failed: missing authentication ticket!", "danger")
        redirect(url_for('user_views.root'))
                
    # validate ticket and get username by calling verify_ticket
    username, attributes, pgtiou = current_app.cas_client.verify_ticket(ticket)

    #print('CAS verify ticket response: username: %s, attributes: %s, pgtiou: %s', username, attributes, pgtiou)

    if not username:
        # verifying ticket failed so send them to the homepage
        flash("Login process failed: authentication failed!", "danger")
        redirect(url_for('user_views.root'))


    with current_app.Session() as session:
        # try to find the username in our database
        matching_user = (
            session.query(db_models.User)
                .filter(db_models.User.username == username)
                .first()
        )

        if not matching_user:
            # couldn't find this user in our database
            flash("Login process failed: unauthorized user!", "danger")
            redirect(url_for('user_views.root'))
        else:
            # login process complete!
            login_user(matching_user)
            flash(f"You have successfully signed in as {username}!", "success")
            if next_url is None:
                return redirect(url_for('user_views.root'))
            else:
                return redirect(next_url)


@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("You've successfully logged out!", "success")

        redirect_url = url_for('user_views.root', _external=True)
        cas_logout_url = current_app.cas_client.get_logout_url(redirect_url)
        #print('CAS logout URL: %s', cas_logout_url)

        return redirect(cas_logout_url)
    else:
        flash("You must be signed in before you can log out!", "warning")
        return redirect(url_for('user_views.root'))
