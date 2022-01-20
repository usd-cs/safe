FROM python:3.9-slim-buster

RUN apt-get update
RUN apt-get -y install vim

RUN adduser --system --group --uid 1000 safe

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

EXPOSE 6000
ENTRYPOINT ["./boot-webapp.sh"]
