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

from . import cli, wsgi
from .morss import MorssException


def main():
    if 'REQUEST_URI' in os.environ:
        # mod_cgi (w/o file handler)
        wsgi.cgi_handle_request()

    elif len(sys.argv) <= 1:
        # start internal (basic) http server (w/ file handler)
        wsgi.cgi_start_server()

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
