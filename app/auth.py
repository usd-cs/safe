from flask import (
    Blueprint, render_template, abort, current_app, request, redirect, url_for,
    flash
)
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SubmitField, PasswordField
)
from wtforms.validators import DataRequired

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
                return redirect(url_for('root'))
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

    return redirect(url_for('root'))


