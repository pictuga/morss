FROM alpine:latest

RUN apk add --no-cache python3 py3-pip py3-wheel git py3-lxml py3-gevent py3-zope-interface py3-zope-event

ADD . /app
RUN pip3 install --no-cache-dir /app[full] gunicorn

USER 1000:1000

ENTRYPOINT ["/bin/sh", "/app/docker-entry.sh"]
CMD ["run"]
