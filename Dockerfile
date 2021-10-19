FROM alpine:latest

RUN apk add --no-cache python3 py3-lxml py3-pip py3-wheel git

ADD . /app
RUN pip3 install --no-cache-dir /app[full] gunicorn

USER 1000:1000

CMD gunicorn --bind 0.0.0.0:8000 -w 4 --preload --access-logfile - morss
