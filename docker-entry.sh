#! /bin/sh

if [ -z "$1" ] || [ "$@" = "run" ]; then
	gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 4 --worker-class=gevent --preload --access-logfile - morss
else
	morss $@
fi
