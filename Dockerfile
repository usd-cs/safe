FROM python:alpine3.14
ARG FIRST_ADMIN_USER

RUN apk add build-base
RUN apk add libxml2-dev
RUN apk add libxslt-dev

RUN adduser -D --uid 1000 safe

RUN mkdir /safe
RUN mkdir /safe/instance

WORKDIR /safe

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn

COPY app app
COPY safe.py config.py boot-webapp.sh boot-worker.sh ./
COPY instance_config.py instance/config.py
RUN chmod +x boot-webapp.sh boot-worker.sh

ENV FLASK_APP safe.py

RUN chown -R safe:safe ./
USER safe

RUN flask add-admin $FIRST_ADMIN_USER

EXPOSE 5000
ENTRYPOINT ["./boot-webapp.sh"]
