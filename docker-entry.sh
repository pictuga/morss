#! /bin/sh

if [ ! -z "$1" ]; then
	morss $@
else
	gunicorn --bind 0.0.0.0:8000 -w 4 --preload --access-logfile - morss
fi
