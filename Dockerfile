FROM python:3.6-alpine

RUN adduser -D app

RUN mkdir /safe
RUN mkdir /safe/instance

WORKDIR /safe

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn

COPY app app
COPY safe.py config.py boot.sh ./
COPY instance_config.py instance/config.py
RUN chmod +x boot.sh

ENV FLASK_APP safe.py

RUN chown -R safe:safe ./
USER safe

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]
