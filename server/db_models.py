from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from flask_login import UserMixin

from werkzeug.security import check_password_hash


engine = create_engine('sqlite:///safe.db', echo=True)
Base = declarative_base()

student_team = Table(
    "student_team",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("student.student_id")),
    Column("team_id", Integer, ForeignKey("team.team_id")),
)

class Instructor(UserMixin, Base):
    __tablename__ = "instructor"
    instructor_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    sections = relationship("Section", backref=backref("instructor"))

    def get_id(self):
        return self.instructor_id

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Section(Base):
    __tablename__ = "section"
    section_id = Column(Integer, primary_key=True)
    instructor_id = Column(Integer, ForeignKey("instructor.instructor_id"))
    teams = relationship("Team", backref=backref("section"))
    students = relationship("Student", backref=backref("section"))

class PSA(Base):
    __tablename__ = "psa"
    psa_id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    files = relationship("SourceFile", backref=backref("psa"))
    teams = relationship("Team", backref=backref("psa"))

class Student(UserMixin, Base):
    __tablename__ = "student"
    student_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    section_id = Column(Integer, ForeignKey("section.section_id"))
    teams = relationship(
        "Team", secondary=student_team, back_populates="students"
    )

    def get_id(self):
        return str(self.student_id)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Team(Base):
    __tablename__ = "team"
    team_id = Column(Integer, primary_key=True)
    team_num = Column(Integer, nullable=False)
    psa_id = Column(Integer, ForeignKey("psa.psa_id"))
    section_id = Column(Integer, ForeignKey("section.section_id"))
    students = relationship(
        "Student", secondary=student_team, back_populates="teams"
    )

class SourceFile(Base):
    __tablename__ = "source_file"
    source_file_id = Column(Integer, primary_key=True)
    psa_id = Column(Integer, ForeignKey("psa.psa_id"))
    filename = Column(String, nullable=False)

# create tables
Base.metadata.create_all(engine)
