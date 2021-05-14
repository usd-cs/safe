FROM docker.io/alpine:latest

RUN apk update
RUN apk add git
RUN apk add openssh
RUN apk add python3
RUN apk add py3-pip
RUN apk add py3-numpy
RUN apk add py3-scipy
RUN apk add py3-matplotlib
RUN apk add py3-flask
RUN apk add py3-flask-wtf
RUN apk add py3-flask-login
RUN apk add py3-jinja2
RUN apk add py3-sqlalchemy
RUN apk add py3-pillow
RUN apk add sqlite

# copy server files
COPY raft_server.py /var/raft/
COPY server/db_models.py /var/raft/
COPY server/templates /var/raft/templates
COPY server/raft.db /var/raft/

RUN git config --global pull.rebase false

EXPOSE 6000
WORKDIR /var/raft
CMD python3 raft_server.py
