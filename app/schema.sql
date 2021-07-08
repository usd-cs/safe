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

INSERT INTO instructor (instructor_id, username, password) VALUES (1, 'jenniferolsen', 'pbkdf2:sha256:150000$EuQeJ1XU$313eac1719a86ca2445bf53a728461fb2164c1805192e6090320569dd6722b0d');
INSERT INTO instructor (instructor_id, username, password) VALUES (2, 'sat', 'pbkdf2:sha256:150000$AbTdlcM7$1e0cdd48fea0d4e7cc2969e369a873cdd50d624dde01bf95070ef7684d6d7cca');
INSERT INTO instructor (instructor_id, username, password) VALUES (4, 'jsixt', 'pbkdf2:sha256:150000$9GRTB1Ss$9bcb774ff392ea310a87110563214c7c6e230874b30781193a92bef38e08b6b3');

INSERT INTO section (section_id, instructor_id) VALUES (1, 1);
INSERT INTO section (section_id, instructor_id) VALUES (2, 2);
INSERT INTO section (section_id, instructor_id) VALUES (4, 4);

INSERT INTO psa (psa_id, title) VALUES (0, 'Working with Git');
INSERT INTO source_file (psa_id, filename) VALUES (0, '*.txt');

INSERT INTO psa (psa_id, title) VALUES (1, 'Turtle Name Drawer');
INSERT INTO source_file (psa_id, filename) VALUES (1, 'name_drawer.py');

INSERT INTO psa (psa_id, title) VALUES (2, 'Digital Audio Filters');
INSERT INTO source_file (psa_id, filename) VALUES (2, 'audio_filters.py');

INSERT INTO psa (psa_id, title) VALUES (3, 'Hurricane Tracking and Sentiment Analysis');
INSERT INTO source_file (psa_id, filename) VALUES (3, 'hurricane_tracker.py');
INSERT INTO source_file (psa_id, filename) VALUES (3, 'movie_sentiment.py');

INSERT INTO psa (psa_id, title) VALUES (4, 'Song Generator');
INSERT INTO source_file (psa_id, filename) VALUES (4, 'song_generator.py');

INSERT INTO psa (psa_id, title) VALUES (5, 'Data Analysis and Visualization');
INSERT INTO source_file (psa_id, filename) VALUES (5, 'data_analyzer.py');

INSERT INTO psa (psa_id, title) VALUES (6, 'Purple America');
INSERT INTO source_file (psa_id, filename) VALUES (6, 'purple_america.py');

INSERT INTO psa (psa_id, title) VALUES (7, 'Game of Sticks');
INSERT INTO source_file (psa_id, filename) VALUES (7, 'game_of_sticks.py');

INSERT INTO psa (psa_id, title) VALUES (8, 'Collage');
INSERT INTO source_file (psa_id, filename) VALUES (8, 'collage_creator.py');

INSERT INTO psa (psa_id, title) VALUES (9, 'Critters');
INSERT INTO source_file (psa_id, filename) VALUES (9, 'critters.py');

