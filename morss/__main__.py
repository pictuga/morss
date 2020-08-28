# This file is part of morss
#
# Copyright (C) 2013-2020 pictuga <contact@pictuga.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.

# ran on `python -m morss`

import os
import sys

from . import wsgi
from . import cli

from .morss import MorssException

import wsgiref.simple_server
import wsgiref.handlers


PORT = int(os.getenv('PORT', 8080))


def main():
    if 'REQUEST_URI' in os.environ:
        # mod_cgi (w/o file handler)

        app = wsgi.cgi_app
        app = wsgi.cgi_dispatcher(app)
        app = wsgi.cgi_error_handler(app)
        app = wsgi.cgi_encode(app)

        wsgiref.handlers.CGIHandler().run(app)

    elif len(sys.argv) <= 1:
        # start internal (basic) http server (w/ file handler)

        app = wsgi.cgi_app
        app = wsgi.cgi_file_handler(app)
        app = wsgi.cgi_dispatcher(app)
        app = wsgi.cgi_error_handler(app)
        app = wsgi.cgi_encode(app)

        print('Serving http://localhost:%s/' % PORT)
        httpd = wsgiref.simple_server.make_server('', PORT, app)
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
