#! /bin/sh

if [ "$1" = "sh" ] || [ "$1" = "bash" ]; then
	exec $@

elif [ -z "$1" ] || [ "$@" = "run" ]; then
	gunicorn --bind 0.0.0.0:${PORT:-8000} ${GUNICORN:---workers 4 --threads 4} --preload --access-logfile - morss

else
	morss $@

fi
