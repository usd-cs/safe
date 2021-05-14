CREATE TABLE instructor (
    instructor_id INTEGER NOT NULL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password VARCHAR NOT NULL
);

CREATE TABLE section (
    section_id INTEGER NOT NULL PRIMARY KEY,
    instructor_id INTEGER REFERENCES instructor
);

CREATE TABLE student (
    student_id INTEGER NOT NULL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password VARCHAR NOT NULL,
    section_id INTEGER REFERENCES section
);

CREATE TABLE psa (
    psa_id INTEGER NOT NULL PRIMARY KEY,
    title VARCHAR NOT NULL
);

CREATE TABLE team (
    team_id INTEGER NOT NULL PRIMARY KEY,
	team_num INTEGER NOT NULL,
    psa_id INTEGER REFERENCES psa,
    section_id INTEGER REFERENCES section,
    CONSTRAINT uc_teaminfo UNIQUE (team_num, psa_id, section_id)
);

CREATE TABLE source_file (
    source_file_id INTEGER NOT NULL PRIMARY KEY,
    psa_id INTEGER REFERENCES psa,
    filename VARCHAR NOT NULL
);

CREATE TABLE student_team (
    student_id INTEGER REFERENCES student,
    team_id INTEGER REFERENCES team
);
