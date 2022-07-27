"""
Mock implementation of a CAS server. This should be used only during testing
to avoid having to go to any external servers during login.
"""

from flask import (
    Blueprint, render_template, abort, request, redirect, url_for
)
from flask_wtf import FlaskForm
from wtforms.validators import (
    DataRequired, Regexp
)
from wtforms import StringField, PasswordField, SubmitField
from urllib.parse import urlparse

cas = Blueprint('cas', __name__)

def verify_mock_ticket(ticket):
    import re
    m = re.match("ST-mock-([a-zA-Z]\w*)", ticket)
    if not m:
        return None, {}, None
    else:
        return m.group(1), {}, None

@cas.route('/')
def mock_cas_home():
    return "Mock CAS Server"

@cas.route('/login', methods=['GET', 'POST'])
def mock_cas_login():
    service_url = request.args.get('service')
    if not service_url:
        abort(404)

    form = MockCASLoginForm()

    if form.validate_on_submit():
        redirect_url = url_for('auth.verify_ticket', ticket=f"ST-mock-{form.username.data}")

        p = urlparse(service_url)
        if p.query:
            redirect_url += ('&' + p.query)

        return redirect(redirect_url)

    return render_template("cas_mock_login.html", form=form)
    
@cas.route('/logout')
def mock_cas_logout():
    service_url = request.args.get('service')
    if not service_url:
        abort(404)

    return redirect(service_url)

class MockCASLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Regexp("[a-zA-Z]\w*")])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

