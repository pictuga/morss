#! /bin/sh

if [ -z "$1" ] || [ "$@" = "run" ]; then
	gunicorn --bind 0.0.0.0:${PORT:-8000} -w 4 --preload --access-logfile - morss
else
	morss $@
fi
