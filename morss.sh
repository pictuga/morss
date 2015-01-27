#! /bin/sh
### BEGIN INIT INFO
# Provides:          morss
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Should-Start:      $python $uwsgi
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: virtualenv + uwsgi + morss debian init script
# Description:       virtualenv + uwsgi + morss debian init script
### END INIT INFO

# Borrowed from: http://kuttler.eu/code/debian-init-script-virtualenv-gunicorn-django/
# Borrowed from: https://gist.github.com/leplatrem/5684206
# Please remove the "Author" lines above and replace them
# with your own name if you copy and modify this script.
#
# Enable with update-rc.d gunicorn-example start 30 2 3 4 5 . stop 70 0 1 6 .
# (parameters might not be necessary, test)

# Do NOT "set -e"

PROJECT=/var/www/morss
VIRTUALENV=/var/www/morss/morss_venv
LOGDIR=/var/log/
# PATH should only include /usr/* if it runs after the mountnfs.sh script
PATH=/bin:/usr/bin
USER=www-data
GROUP=www-data
IP=0.0.0.0
PORT=8080
MORSSFILE=morss.py
CALLABLE=cgi_wrapper
PROCESSES=5
# I am lazy and just call the init script gunicorn-project
NAME=morss
DESC=$NAME
LOGFILE="$LOGDIR$NAME.log"
PIDFILE="$PROJECT$NAME.pid"
CMD="uwsgi --uid $USER --gid $GROUP --socket $IP:$PORT --wsgi-file $MORSSFILE --callable $CALLABLE --processes $PROCESSES --daemonize $LOGFILE --pidfile $PIDFILE --master --enable-threads"

# Load the VERBOSE setting and other rcS variables
. /lib/init/vars.sh

# Define LSB log_* functions.
# Depend on lsb-base (>= 3.2-14) to ensure that this file is present
# and status_of_proc is working.

. /lib/lsb/init-functions
 
 
if [ -e "/etc/default/$NAME" ]
then
    . /etc/default/$NAME
fi
 
 
case "$1" in
  start)
        log_daemon_msg "Starting deferred execution scheduler" "$NAME"
        source $ACTIVATE
        $CMD
        log_end_msg $?
    ;;
  stop)
        log_daemon_msg "Stopping deferred execution scheduler" "NAME"
        killproc -p $PIDFILE $NAME
        log_end_msg $?
    ;;
  force-reload|restart)
    $0 stop
    $0 start
    ;;
  status)
    status_of_proc -p $PIDFILE $NAME && exit 0 || exit $?
    ;;
  *)
    echo "Usage: /etc/init.d/$NAME {start|stop|restart|force-reload|status}"
    exit 1
    ;;
esac
 
exit 0
