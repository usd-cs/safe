from sqlalchemy import (
        Column, Integer, String, Boolean, ForeignKey, Table, TIMESTAMP,
        LargeBinary
        )
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from flask_login import UserMixin
import datetime

from werkzeug.security import check_password_hash

Base = declarative_base()

# Intermediate entity for many-many relationship between users and groups (AKA teams)
team_enrollment = Table(
    "team_enrollment",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.user_id")),
    Column("team_id", Integer, ForeignKey("team.team_id")),
)

# Intermediate entity for many-many relationship between users and sections
section_enrollment = Table(
    "section_enrollment",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.user_id")),
    Column("section_id", Integer, ForeignKey("section.section_id")),
)

# TODO: make columns unique=True where appropriate

class User(UserMixin, Base):
    __tablename__ = "user"
    user_id = Column(Integer, primary_key=True)
    admin = Column(Boolean, nullable=False, default=False)
    instructor = Column(Boolean, nullable=False, default=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)

    # setting up many-to-many relationships
    sections = relationship(
        "Section", secondary=section_enrollment, back_populates="users"
    )
    teams = relationship(
        "Team", secondary=team_enrollment, back_populates="members"
    )

    # The following functions are used for login
    def get_id(self):
        return self.user_id

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Section(Base):
    __tablename__ = "section"
    section_id = Column(Integer, primary_key=True)
    course = Column(String, nullable=False)
    semester = Column(String, nullable=False)
    section_num = Column(Integer, nullable=False)

    # many-to-many relationship
    users = relationship(
        "User", secondary=section_enrollment, back_populates="sections"
    )

    # one section to many assignments
    assignments = relationship("Assignment", backref=backref("section"))


class Assignment(Base):
    __tablename__ = "assignment"
    assignment_id = Column(Integer, primary_key=True)
    num = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    tester_run_command = Column(String, nullable=False)
    # TODO: add deadline column?

    section_id = Column(Integer, ForeignKey("section.section_id"))

    # one assignment has many files and teams
    files = relationship("SourceFile", backref=backref("assignment"))
    tester_files = relationship("TesterFile", backref=backref("assignment"))
    teams = relationship("Team", backref=backref("assignment"))


class Team(Base):
    __tablename__ = "team"
    team_id = Column(Integer, primary_key=True)
    team_num = Column(Integer, nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignment.assignment_id"))

    # one team may have many test results
    results = relationship("TestResults", backref=backref("team"))

    # many-to-many relationship between teams and users
    members = relationship(
        "User", secondary=team_enrollment, back_populates="teams"
    )

    def __repr__(self):
        return f"Team(team_id={self.team_id}, team_num={self.team_num}, assignment_id={self.assignment_id})"


class TestResults(Base):
    __tablename__ = "test_results"
    job_id = Column(String, primary_key=True)
    finished = Column(Boolean, nullable=False, default=False)
    results = Column(String)
    commit_time = Column(TIMESTAMP)
    commit_comment = Column(String)
    commit_author = Column(String)
    completed_at = Column(TIMESTAMP)

    team_id = Column(Integer, ForeignKey("team.team_id"))


class SourceFile(Base):
    __tablename__ = "source_file"
    source_file_id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignment.assignment_id"))


# TODO: add content_type column
class TesterFile(Base):
    __tablename__ = "tester_file"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignment.assignment_id"))


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_request"
    request_id = Column(Integer, primary_key=True)
    hashed_id = Column(String, nullable=False)
    time = Column(TIMESTAMP, default=datetime.datetime.now, nullable=False)

    user_id = Column(Integer, ForeignKey("user.user_id"))
