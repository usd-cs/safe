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
COPY server/safe_server.py /var/safe/
COPY server/db_models.py /var/safe/
COPY server/templates /var/safe/templates
COPY server/safe.db /var/safe/

RUN git config --global pull.rebase false

EXPOSE 6000
WORKDIR /var/safe
CMD python3 safe_server.py
