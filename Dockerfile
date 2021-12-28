FROM alpine:edge

ADD . /app

RUN set -ex; \
	apk add --no-cache --virtual .run-deps python3 py3-lxml py3-setproctitle py3-setuptools; \
	apk add --no-cache --virtual .build-deps py3-pip py3-wheel; \
	pip3 install --no-cache-dir /app[full]; \
	apk del .build-deps

USER 1000:1000

ENTRYPOINT ["/bin/sh", "/app/morss-helper"]
CMD ["run"]

HEALTHCHECK CMD /bin/sh /app/morss-helper check
