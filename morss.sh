#! /bin/sh
### BEGIN INIT INFO
# Provides:          morss
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Should-Start:      $python $uwsgi
# Default-Start:     30 2 3 4 5
# Default-Stop:      70 0 1 6
# Short-Description: virtualenv + uwsgi + morss debian init script
# Description:       virtualenv + uwsgi + morss debian init script
### END INIT INFO

# Borrowed from: http://kuttler.eu/code/debian-init-script-virtualenv-gunicorn-django/
# Please remove the "Author" lines above and replace them
# with your own name if you copy and modify this script.
#
# Enable with update-rc.d gunicorn-example start 30 2 3 4 5 . stop 70 0 1 6 .
# (parameters might not be necessary, test)

# Do NOT "set -e"

PROJECT=/var/www/morss
VIRTUALENV=/var/www/morss/morss_venv
LOGDIR=/var/log/morss/
# PATH should only include /usr/* if it runs after the mountnfs.sh script
PATH=/bin:/usr/bin
USER=www-data
GROUP=www-data
# I am lazy and just call the init script gunicorn-project
NAME=morss
DESC=$NAME
LOGFILE="$LOGDIR$NAME.log"
PIDFILE="$PROJECT$NAME.pid"
CMD="uwsgi --ini /morss/uwsgi.ini"

# Load the VERBOSE setting and other rcS variables
. /lib/init/vars.sh

# Define LSB log_* functions.
# Depend on lsb-base (>= 3.2-14) to ensure that this file is present
# and status_of_proc is working.
. /lib/lsb/init-functions

#
# Function that starts the daemon/service
#
do_start() {
  # Return
  #   0 if daemon has been started
  #   1 if daemon was already running
  #   2 if daemon could not be started
  if [ -e $PIDFILE ]; then
    return 1
  fi
  cd $PROJECT
  source $VIRTUALENV/bin/activate
  $CMD
  if [ $? = 0 ]; then
    return 0
  else
    return 2
  fi
}

#
# Function that stops the daemon/service
#
do_stop() {
  # Return
  #   0 if daemon has been stopped
  #   1 if daemon was already stopped
  #   2 if daemon could not be stopped
  #   other if a failure occurred
  if [ -f $PIDFILE ]; then
    PID=`cat $PIDFILE`
    rm $PIDFILE
    kill -15 $PID
    if [ $? = 0 ]; then
      return 0
    else
      return 2
    fi
  else
    return 1
  fi
}

do_reload() {
  if [ -f $PIDFILE ]; then
    PID=`cat $PIDFILE`
    kill -HUP $PID
    return $?
  fi
  return 2
}

case "$1" in
  start)
  [ "$VERBOSE" != no ] && log_daemon_msg "Starting $DESC" "$NAME"
  do_start
  case "$?" in
    0|1) [ "$VERBOSE" != no ] && log_end_msg 0 ;;
    2) [ "$VERBOSE" != no ] && log_end_msg 1 ;;
  esac
  ;;
  stop)
  [ "$VERBOSE" != no ] && log_daemon_msg "Stopping $DESC" "$NAME"
  do_stop
  case "$?" in
    0|1) [ "$VERBOSE" != no ] && log_end_msg 0 ;;
    2) [ "$VERBOSE" != no ] && log_end_msg 1 ;;
  esac
  ;;
  restart)
  log_daemon_msg "Restarting $DESC" "$NAME"
  do_stop
  case "$?" in
    0|1)
    do_start
    case "$?" in
      0) log_end_msg 0 ;;
      1) log_end_msg 1 ;; # Old process is still running
      *) log_end_msg 1 ;; # Failed to start
    esac
    ;;
    *)
      # Failed to stop
    log_end_msg 1
    ;;
  esac
  ;;
  reload)
  log_daemon_msg "Reloading $DESC" "$NAME"
  do_reload
  case "$?" in
    0) log_end_msg 0 ;;
    *) log_end_msg 1 ;;
  esac
  ;;
  *)
  echo "Usage: $SCRIPTNAME {start|stop|restart|reload}" >&2
  exit 3
  ;;
esac

:
