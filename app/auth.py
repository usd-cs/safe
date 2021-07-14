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


class LoginForm(FlaskForm):
    username = StringField(label=('Username'), validators=[DataRequired()])
    password = PasswordField(label=('Password'), validators=[DataRequired()])
    submit = SubmitField(label=('Submit'))

@auth.route('/login/', methods = ['POST', 'GET'])
def login():
    if current_user.is_authenticated:
        next_url = request.args.get('next')
        if next_url is None:
            flash(f"You are already logged in as {current_user.username}", "warning")
            return redirect(url_for('root'))
        else:
            print(next_url)
            return redirect(next_url)

    form = LoginForm()
    if form.validate_on_submit():
        with current_app.Session() as session:
            user_matches = (
                session.query(db_models.User)
                    .filter(db_models.User.username == form.username.data)
            )

        if user_matches.count() == 1:
            matching_user = user_matches.first()
        else:
            matching_user = None

        if matching_user is None or not matching_user.check_password(form.password.data):
            # TODO: log invalid attempts
            flash("Invalid username or password!", "danger")
        else:
            login_user(matching_user)
            next_url = request.args.get('next')
            if next_url is None:
                flash("You've successfully signed in!", "success")
                return redirect(url_for('user_views.root'))
            else:
                return redirect(next_url)

    return render_template('login.html', form=form)

@auth.route('/logout/')
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("You've successfully logged out!", "success")
    else:
        flash("You must be signed in before you can log out!", "warning")
        pass

    return redirect(url_for('user_views.root'))


class PasswordResetForm(FlaskForm):
    password = PasswordField('Password', validators=[InputRequired(),
                                                        Length(min=10, max=30),
                                                        EqualTo('confirm_password')])
    confirm_password = PasswordField('Repeat Password')
    submit = SubmitField('Submit')

@auth.route("/reset_password", methods=['get', 'post'])
def reset_password():
    token = request.args.get('token')
    if not token:
        return render_template("bad_token.html",
                                invalid_reason="Missing token")

    hashed_token = hashlib.sha1(token.encode('utf-8')).hexdigest()

    with current_app.Session() as session:
        existing_request = (
            session.query(db_models.PasswordResetRequest)
                .filter(db_models.PasswordResetRequest.hashed_id == hashed_token)
                .first()
        )

        if not existing_request:
            return render_template("bad_token.html",
                                    invalid_reason="Token does not exist")

        # check expiry date for password reset request
        time_diff = (datetime.datetime.now() - existing_request.time).total_seconds()

        if time_diff > 60 * current_app.config['MAX_PASSWORD_RESET_TIME']:
            session.delete(existing_request)
            session.commit()

            return render_template("bad_token.html",
                                    invalid_reason="Token has expired!")

        form = PasswordResetForm()

        if form.validate_on_submit():
            # remove request from table and update User with new password
            session.delete(existing_request)
            session.commit()

            user = (
                session.query(db_models.User)
                    .filter(db_models.User.user_id == existing_request.user_id)
                    .first()
            )

            if not user:
                abort(500)

            user.password = generate_password_hash(form.password.data)
            session.commit()

            flash("Password has been successfully reset.", "info")
            return redirect(url_for('auth.login'))

        return render_template("reset_password.html",
                                page_title="Password Reset: SAFE @ USD",
                                form=form)

class ForgotPasswordForm(FlaskForm):
    username = StringField('USD Username', validators=[DataRequired()])
    submit = SubmitField('Submit')

def send_password_recovery_email(user, token, email_address=None):
    message = MIMEMultipart("alternative")
    message["Subject"] = "SAFE Password Reset Request"

    # TODO: use email.utils.formataddr for from/to/reply-to
    message["From"] = current_app.config['EMAIL_ACCOUNT']

    if email_address:
        to_address = email_address
    else:
        # TODO: make domain configurable
        to_address = user.username + "@sandiego.edu"

    message["To"] = to_address
    message["Reply-To"] = current_app.config['EMAIL_ACCOUNT_NOREPLY']

    reset_link = current_app.config['SERVER_BASE_URL'] + url_for('.reset_password', token=token)

    message_text = f"""\
    We have received a request to reset your SAFE @ USD password.

    Please visit the following webpage within 15 minutes to reset your password.

    {reset_link}

    If you did not initiate this request, please contact your instructor immediately."""

    message_html = f"""\
    <html>
    <body>
    <p>We have received a request to reset your SAFE @ USD password.</p>

    <p>
    Please visit the following webpage within <strong>15 minutes</strong> to reset your password.
    </p>

    <p><a href="{reset_link}">{reset_link}</a></p>

    <p>If you did not initiate this request, please contact your instructor
    immediately.</p>

    </body>
    </html>"""

    part1 = MIMEText(message_text, "plain")
    part2 = MIMEText(message_html, "html")
    message.attach(part1)
    message.attach(part2)

    context = ssl.create_default_context()
    with smtplib.SMTP(current_app.config['SMTP_SERVER'], current_app.config['SMTP_PORT']) as server:
        server.starttls(context=context)
        server.login(current_app.config['EMAIL_ACCOUNT'], current_app.config['SMTP_PASSWORD'])
        server.sendmail(current_app.config['EMAIL_ACCOUNT'],
                                    user.username + "@sandiego.edu",
                                    message.as_string())


def create_password_request(username, session, email_recipient=None):
    token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha1(token.encode('utf-8')).hexdigest()

    # TODO: log reset requests
    user = (
        session.query(db_models.User)
            .filter(db_models.User.username == username)
            .first()
    )

    if user:
        # check if there is an existing request and handle appropriately
        existing_request = (
            session.query(db_models.PasswordResetRequest)
                .filter(db_models.PasswordResetRequest.user_id == user.user_id)
                .first()
        )

        if existing_request:
            time_diff = (datetime.datetime.now() - existing_request.time).total_seconds()

            if time_diff > 60 * current_app.config['MAX_PASSWORD_RESET_TIME']:
                # If request is old, delete it.
                session.delete(existing_request)
                session.commit()
            else:
                # If old request is still valid, flash message reminding user
                # to check their email for the previous password reset request
                flash(("You recently requested a password reset. "
                        "Please check your USD email for the link, including your Spam folder."),
                        "warning")
                return


        if current_app.config['EMAIL_ENABLED']:
            send_password_recovery_email(user, token,
                                            email_address=email_recipient)
        else:
            print("Password reset URL:", 
                    current_app.config['SERVER_BASE_URL'] + url_for('.reset_password', token=token))

        new_request = db_models.PasswordResetRequest(hashed_id=hashed_token,
                                                        user_id=user.user_id)

        session.add(new_request)
        session.commit()

        flash(("An email has been sent to your USD email address with " 
                "instructions on resetting your password. You have "
                f"{current_app.config['MAX_PASSWORD_RESET_TIME']} minutes to "
                "complete the process."), 
                    "warning")


@auth.route("/forgot_password", methods=['get', 'post'])
def forgot_password():
    form = ForgotPasswordForm()

    if form.validate_on_submit():
        with current_app.Session() as session:
            create_password_request(form.username.data, session)

            return redirect(url_for('user_views.root'))

    return render_template("forgot_password.html",
                            page_title="Forgot Password: SAFE @ USD",
                            form=form)
    
