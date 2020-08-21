# ran on `python -m morss`

import os
import sys

from . import cgi
from . import cli

from .morss import MorssException

import wsgiref.simple_server
import wsgiref.handlers


PORT = 8080


def isInt(string):
    try:
        int(string)
        return True

    except ValueError:
        return False


def main():
    if 'REQUEST_URI' in os.environ:
        # mod_cgi

        app = cgi.cgi_app
        app = cgi.cgi_dispatcher(app)
        app = cgi.cgi_error_handler(app)
        app = cgi.cgi_encode(app)

        wsgiref.handlers.CGIHandler().run(app)

    elif len(sys.argv) <= 1 or isInt(sys.argv[1]):
        # start internal (basic) http server

        if len(sys.argv) > 1 and isInt(sys.argv[1]):
            argPort = int(sys.argv[1])
            if argPort > 0:
                port = argPort

            else:
                raise MorssException('Port must be positive integer')

        else:
            port = PORT

        app = cgi.cgi_app
        app = cgi.cgi_file_handler(app)
        app = cgi.cgi_dispatcher(app)
        app = cgi.cgi_error_handler(app)
        app = cgi.cgi_encode(app)

        print('Serving http://localhost:%s/' % port)
        httpd = wsgiref.simple_server.make_server('', port, app)
        httpd.serve_forever()

    else:
        # as a CLI app
        try:
            cli.cli_app()

        except (KeyboardInterrupt, SystemExit):
            raise

        except Exception as e:
            print('ERROR: %s' % e.message)

if __name__ == '__main__':
    main()
