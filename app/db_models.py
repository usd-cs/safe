import os, json

from sqlalchemy import (
        Column, Integer, String, Boolean, ForeignKey, Table, TIMESTAMP,
        LargeBinary
        )
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from flask import Markup
from flask_login import UserMixin
import datetime
from werkzeug.utils import secure_filename

from app import db

#Base = declarative_base()

"""
enrollments = db.Table(
    'enrollments',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'),
              primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'),
              primary_key=True)
)
"""

# Intermediate entity for many-many relationship between users and groups (AKA teams)
team_enrollment = db.Table(
    "team_enrollment",
    db.Column("user_id", db.Integer, db.ForeignKey("user.user_id")),
    db.Column("team_id", db.Integer, db.ForeignKey("team.team_id")),
)

# Intermediate entity for many-many relationship between users and sections
section_enrollment = db.Table(
    "section_enrollment",
    db.Column("user_id", db.Integer, db.ForeignKey("user.user_id")),
    db.Column("section_id", db.Integer, db.ForeignKey("section.section_id")),
)


class User(UserMixin, db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    admin = db.Column(db.Boolean, nullable=False, default=False)
    instructor = db.Column(db.Boolean, nullable=False, default=False)
    username = db.Column(db.String, nullable=False, unique=True)
    first_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String, nullable=False)

    # setting up many-to-many relationships
    sections = db.relationship('Section',
                               secondary=section_enrollment,
                               primaryjoin=('section_enrollment.c.user_id == User.user_id'),
                               secondaryjoin=('section_enrollment.c.section_id == Section.section_id'),
                               backref=db.backref('users', lazy='dynamic'),
                               lazy='dynamic')

    teams = db.relationship('Team',
                            secondary=team_enrollment,
                            primaryjoin=('team_enrollment.c.user_id == User.user_id'),
                            secondaryjoin=('team_enrollment.c.team_id == Team.team_id'),
                            backref=db.backref('members', lazy='dynamic'),
                            lazy='dynamic')

    # The following functions are used for login
    def get_id(self):
        return self.user_id


class Section(db.Model):
    section_id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String, nullable=False)
    semester = db.Column(db.String, nullable=False)
    section_num = db.Column(db.Integer, nullable=False)

    # one section may have many assignments
    assignments = db.relationship('Assignment',
                                    foreign_keys='Assignment.section_id',
                                    backref='section', lazy='dynamic',
                                    order_by='Assignment.num')

    def instructors(self):
        """ Returns all of the instructors for this section. """
        return self.users.filter_by(instructor=True).all()

    def is_instructor(self, user):
        """ Returns true if the given user is an instructor for this section. """
        return self.users.filter_by(instructor=True, user_id=user.user_id).count() == 1

    def students(self):
        """ Returns all of the instructors for this section. """
        return self.users.filter_by(instructor=False).all()

    def num_students(self):
        """ Returns the number of students enrolled in this section. """
        return self.users.filter_by(instructor=False).count()

    def num_instructors(self):
        """ Returns the number of instructors for this section. """
        return self.users.filter_by(instructor=True).count()


class BaseAssignment(db.Model):
    assignment_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False, unique=True)
    tester_run_command = db.Column(db.String, nullable=False)
    max_runtime = db.Column(db.Integer, nullable=False)

    # one assignment may have many files (source and tester)
    files = db.relationship('SourceFile',
                            foreign_keys='SourceFile.base_assignment_id',
                            backref='base_assignment',
                            lazy='dynamic')
    tester_files = db.relationship('TesterFile',
                                   foreign_keys='TesterFile.base_assignment_id',
                                   backref='base_assignment',
                                   lazy='dynamic')

    # each assignment can be used by many actual assignments
    assignments = db.relationship('Assignment',
                                  foreign_keys='Assignment.base_assignment_id',
                                  backref='base_assignment',
                                  lazy='dynamic')


class Assignment(db.Model):
    assignment_id = db.Column(db.Integer, primary_key=True)
    num = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)

    section_id = db.Column(db.Integer, db.ForeignKey("section.section_id"))
    base_assignment_id = db.Column(db.Integer, db.ForeignKey("base_assignment.assignment_id"))

    # one assignment can have many teams
    teams = db.relationship('Team',
                            foreign_keys='Team.assignment_id',
                            backref='assignment',
                            order_by="Team.team_num",
                            cascade="all, delete-orphan",
                            lazy='dynamic')


class Team(db.Model):
    team_id = db.Column(db.Integer, primary_key=True)
    team_num = db.Column(db.Integer, nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.assignment_id"))

    # one team may have many test results
    results = db.relationship('TestResults',
                              foreign_keys='TestResults.team_id',
                              backref='team',
                              order_by="TestResults.completed_at.desc()",
                              cascade="all, delete-orphan",
                              lazy='dynamic')

    def __repr__(self):
        return f"Team(team_id={self.team_id}, team_num={self.team_num}, assignment_id={self.assignment_id})"

    def get_latest_results(self):
        """
        Returns the completed test results of the most recent commit. If there
        are multiple results for the same commit, the results with the most
        recent completed_at time will be returned.

        Returns None if there are no completed test results for this team.
        """

        latest_results = (
            self.results.filter_by(finished=True)
                        .order_by(TestResults.commit_time.desc())
                        .order_by(TestResults.completed_at.desc())
                        .first()
        )
        return latest_results


class TestResults(db.Model):
    job_id = db.Column(db.String, primary_key=True)
    finished = db.Column(db.Boolean, nullable=False, default=False)
    results = db.Column(db.String)
    commit_time = db.Column(db.DateTime)
    commit_comment = db.Column(db.String)
    commit_author = db.Column(db.String)
    completed_at = db.Column(db.DateTime)

    team_id = db.Column(db.Integer, db.ForeignKey("team.team_id"))

    # one set of results can have many submitted files
    submitted_files = db.relationship('SubmittedFile',
                                      foreign_keys='SubmittedFile.job_id',
                                      backref='test_results',
                                      order_by="SubmittedFile.filename",
                                      lazy='dynamic')


    def process_results(self):
        """
        Takes the raw results (JSON stored in the results column) and creates
        a set of processed results. These processed results are a dictionary
        that maps the category name (a string) to that that category's
        results. A category's results is a dictionary that tracks:

        - The category number
        - The category name
        - The metrics associated with the category. These are individual unit
          test results, with a description of the metric, its outcome (pass,
          fail, or error) and an optional message (in case of a failed test).
        """

        if not self.results:
            # TODO: make this trigger an exception
            return None

        raw_results = json.loads(self.results)

        processed_results = {}
        for result in raw_results:
            category_results = processed_results.get(result["category_name"])

            if not category_results:
                # Haven't seen this category before so set basic structure up
                # for us (a dictionary with a few items) and add it to our
                # processed results
                category_results = {
                    "category_num": result["category_num"],
                    "category_name": result["category_name"],
                    "metrics": {}
                }

                processed_results[result["category_name"]] = category_results

            # added code to fix errors not showing
            metric_results = category_results["metrics"].get(result["test_num"])

            #if we don't have results or the result it a pass, can rewrite it
            if not metric_results or metric_results['outcome'] == 'pass':

                new_metric = {
                    "description": result["metric"],
                    "outcome": result["outcome"]
                }

                if "message" in result:
                    new_metric["message"] = Markup(result["message"]+"<br>")

                category_results["metrics"][result["test_num"]] = new_metric

            # otherwise we add error messages 
            # (commented out code to just show one error at a time)
            # else:
            #    if "message" in result:
            #        metric_results["message"] += Markup(result["message"]+"<br>")

        return processed_results


    def breakdown_results(self):
        """
        Returns a tuple containing (num passed, num failed, num error) for the
        metrics across all categories in this set of results.
        """

        processed_results = self.process_results()

        num_passed, num_failed, num_error = (0, 0, 0)
        for category_results in processed_results.values():
            for metric_result in category_results.get('metrics', {}).values():
                if metric_result['outcome'] == 'pass':
                    num_passed += 1
                elif metric_result['outcome'] == 'fail':
                    num_failed += 1
                elif metric_result['outcome'] == 'error':
                    num_error += 1

        return (num_passed, num_failed, num_error)



class SubmittedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    job_id = db.Column(db.String, db.ForeignKey("test_results.job_id"))


class SourceFile(db.Model):
    source_file_id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    base_assignment_id = db.Column(db.Integer, db.ForeignKey("base_assignment.assignment_id"))


class TesterFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    filename = db.Column(db.String, nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    # TODO: add content_type column

    base_assignment_id = db.Column(db.Integer, db.ForeignKey("base_assignment.assignment_id"))

    def write_to_file(self, base_dir):
        """ Writes this tester file's data to a file. The file will be located
        in a directory located within the base_dir directory. """
        file_location = os.path.join(base_dir,
                                     f"{self.base_assignment.assignment_id}",
                                     secure_filename(self.filename))

        with open(file_location, 'wb') as new_file:
            new_file.write(self.data)

    def delete(self, base_dir):
        """ Deletes this tester file from the database and from the file
        system (if its data has been written to a file). """

        # remove the file from the tester code directory
        file_path = os.path.join(base_dir,
                                 f"{self.base_assignment.assignment_id}",
                                 secure_filename(self.filename))

        try:
            os.remove(file_path)
        except:
            pass

        # delete from our database
        db.session.delete(self)
        db.session.commit()

