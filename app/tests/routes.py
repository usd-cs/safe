from flask import jsonify, request
from faker import Faker

from app.tests import tests
from app import db
from app.db_models import User

"""
from marshmallow import (
    ValidationError, Schema, fields
)
from random import shuffle, randint
from datetime import date, datetime, timedelta

from app import db
from app.db_models import (
    User, UserSchema, Course, CourseSchema, Assessment, Objective,
    LearningObjectiveSchema, Question,
    ShortAnswerQuestion, ShortAnswerQuestionSchema,
    AutoCheckQuestion, AutoCheckQuestionSchema,
    MultipleChoiceQuestion, MultipleChoiceQuestionSchema, AnswerOption,
    MultipleSelectionQuestion, MultipleSelectionQuestionSchema,
    CodeJumbleQuestion, CodeJumbleQuestionSchema, JumbleBlock, Topic,
    TopicSchema, Textbook, TextbookSchema, TextbookSection
)
"""

Faker.seed(0)
fake = Faker()

@tests.route('/reset_db')
def reset_db():
    db.drop_all()
    db.create_all()
    return jsonify(status="success")


@tests.route('/seed/user', methods=['POST'])
def seed_user():
    json_data = request.get_json()
    if not json_data:
        return jsonify(message="No input data provided"), 400

    user_data = {}
    username = json_data.get('username')
    if username is None:
        return jsonify(message="Missing username"), 400

    user_data['username'] = username.lower()
    user_data['first_name'] = json_data.get("first_name", fake.first_name())
    user_data['last_name'] = json_data.get("last_name", fake.first_name())

    user_data['admin'] = json_data.get('admin', False)
    user_data['instructor'] = json_data.get('instructor', False)

    new_user = User(**user_data)
    db.session.add(new_user)
    db.session.commit()

    print("new user:", user_data)

    return jsonify(user_data)
