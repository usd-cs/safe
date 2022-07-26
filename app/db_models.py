from sqlalchemy import (
        Column, Integer, String, Boolean, ForeignKey, Table, TIMESTAMP,
        LargeBinary
        )
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from flask_login import UserMixin
import datetime

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
    #sections = db.relationship(
    #    "Section", secondary=section_enrollment, back_populates="users"
    #)
    #teams = db.relationship(
    #    "Team", secondary=team_enrollment, back_populates="members"
    #)

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

    # many-to-many relationship
    #users = relationship(
    #    "User", secondary=section_enrollment, order_by="User.last_name", back_populates="sections"
    #)

    # one section to many assignments
    #assignments = db.relationship("Assignment", order_by="Assignment.num", backref=backref("section"))

    assignments = db.relationship('Assignment',
                                    foreign_keys='Assignment.section_id',
                                    backref='section', lazy='dynamic',
                                    order_by='Assignment.num')


class BaseAssignment(db.Model):
    assignment_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False, unique=True)
    tester_run_command = db.Column(db.String, nullable=False)
    max_runtime = db.Column(db.Integer, nullable=False)

    # one assignment potentially has many files (source and tester)
    #files = relationship("SourceFile", backref=backref("base_assignment"))
    #tester_files = relationship("TesterFile", backref=backref("base_assignment"))

    files = db.relationship('SourceFile',
                            foreign_keys='SourceFile.base_assignment_id',
                            backref='base_assignment',
                            lazy='dynamic')
    tester_files = db.relationship('TesterFile',
                                   foreign_keys='TesterFile.base_assignment_id',
                                   backref='base_assignment',
                                   lazy='dynamic')

    # each assignment can be used by many actual assignments
    #assignments = relationship("Assignment", backref=backref("base_assignment"))
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
    """
    teams = relationship("Team", 
                            order_by="Team.team_num",
                            cascade="all, delete-orphan",
                            backref=backref("assignment"))
    """

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
    """
    results = relationship("TestResults",
                            order_by="desc(TestResults.completed_at)",
                            cascade="all, delete-orphan",
                            backref=backref("team"))
    """

    results = db.relationship('TestResults',
                              foreign_keys='TestResults.team_id',
                              backref='team',
                              order_by="TestResults.completed_at.desc()",
                              cascade="all, delete-orphan",
                              lazy='dynamic')

    # many-to-many relationship between teams and users
    """
    members = relationship(
        "User", secondary=team_enrollment, order_by="User.last_name", back_populates="teams"
    )
    """

    def __repr__(self):
        return f"Team(team_id={self.team_id}, team_num={self.team_num}, assignment_id={self.assignment_id})"


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
    """
    submitted_files = relationship("SubmittedFile",
                                    order_by="SubmittedFile.filename",
                                    backref=backref("test_results"))
    """

    submitted_files = db.relationship('SubmittedFile',
                                      foreign_keys='SubmittedFile.job_id',
                                      backref='test_results',
                                      order_by="SubmittedFile.filename",
                                      lazy='dynamic')


class SubmittedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    job_id = db.Column(db.String, db.ForeignKey("test_results.job_id"))


class SourceFile(db.Model):
    source_file_id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    base_assignment_id = db.Column(db.Integer, db.ForeignKey("base_assignment.assignment_id"))


# TODO: add content_type column
class TesterFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    base_assignment_id = db.Column(db.Integer, db.ForeignKey("base_assignment.assignment_id"))

