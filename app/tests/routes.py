from flask import jsonify, request
from faker import Faker
from random import randint

from app.tests import tests
from app import db
from app.db_models import User, Section, SourceFile, TesterFile, BaseAssignment

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
    user_data['last_name'] = json_data.get("last_name", fake.last_name())

    user_data['admin'] = json_data.get('admin', False)
    user_data['instructor'] = json_data.get('instructor', False)

    new_user = User(**user_data)
    db.session.add(new_user)
    db.session.commit()

    print("new user:", user_data)

    return jsonify(user_data)


@tests.route('/seed/section', methods=['POST'])
def seed_section():
    json_data = request.get_json()
    if not json_data:
        return jsonify(message="No input data provided"), 400

    section_data = {}

    instructor_username = json_data.get("instructor_username")
    if instructor_username is None:
        return jsonify(message="Missing instructor_username"), 400

    instructor = User.query.filter_by(username=instructor_username).first()
    if not instructor or instructor.instructor == False:
        return jsonify(message=f"Instructor {instructor_username} does not exist"), 400

    for field in ['course', 'semester', 'section_num']:
        field_value = json_data.get(field)
        if field_value is None:
            return jsonify(message=f"Missing {field}"), 400

        section_data[field] = field_value

    num_students = json_data.get("num_students", 10)

    new_section = Section(**section_data)
    db.session.add(new_section)

    new_section.users.append(instructor)

    students_data = []
    for i in range(num_students):
        u = User(username=f"student{i}", first_name=fake.first_name(),
                 last_name=fake.last_name(), admin=False, instructor=False)
        students_data.append(u.username)
        new_section.users.append(u)

    db.session.commit()

    section_data["student_usernames"] = students_data

    print("new section:", section_data)

    return jsonify(section_data)


@tests.route('/seed/base_assignment', methods=['POST'])
def seed_base_assignment():
    json_data = request.get_json()
    if not json_data:
        return jsonify(message="No input data provided"), 400

    assignment_data = {}

    for field in ['title']:
        field_value = json_data.get(field)
        if field_value is None:
            return jsonify(message=f"Missing {field}"), 400

        assignment_data[field] = field_value

    assignment_data['tester_run_command'] = json_data.get("tester_run_command", "python3 my_tester.py")
    assignment_data['max_runtime'] = json_data.get("max_runtime", 5)

    new_assignment = BaseAssignment(**assignment_data)
    db.session.add(new_assignment)

    new_assignment.files.append(SourceFile(filename=f"{assignment_data['title']}_src1.py"))
    new_assignment.files.append(SourceFile(filename=f"{assignment_data['title']}_src2.py"))

    for i in range(2):
        tester_file = TesterFile(filename=f"{assignment_data['title']}_tester{i}.py",
                                 data=bytes(fake.paragraph(), 'utf-8'))
        new_assignment.tester_files.append(tester_file)

    db.session.commit()

    print("new base assignment:", assignment_data)

    return jsonify(assignment_data)

