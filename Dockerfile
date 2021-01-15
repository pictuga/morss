FROM alpine:latest

RUN apk add --no-cache python3 py3-lxml py3-pip py3-wheel git

ADD . /app
RUN pip3 install --no-cache-dir /app gunicorn

CMD gunicorn --bind 0.0.0.0:8080 -w 4 --preload --access-logfile - morss
