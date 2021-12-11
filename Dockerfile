FROM alpine:latest

ADD . /app

RUN set -ex; \
	apk add --no-cache --virtual .run-deps python3 py3-lxml; \
	apk add --no-cache --virtual .build-deps py3-pip py3-wheel; \
	pip3 install --no-cache-dir /app[full]; \
	apk del .build-deps; \
	rm -r /app

USER 1000:1000

ENTRYPOINT ["/bin/sh", "/app/docker-entry.sh"]
CMD ["run"]
