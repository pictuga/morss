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

import os.path
import sys


def pkg_path(path=''):
    return os.path.join(os.path.dirname(__file__), path)


data_path_base = None


def data_path(path=''):
    global data_path_base

    if data_path_base is not None:
        return os.path.join(data_path_base, path)

    bases = [
        os.path.join(sys.prefix, 'share/morss/www'),
        os.path.join(pkg_path(), './../../../../share/morss/www'),
        os.path.join(pkg_path(), '../www'),
        os.path.join(pkg_path(), '../..')
    ]

    for base in bases:
        full_path = os.path.join(base, path)

        if os.path.isfile(full_path):
            data_path_base = base
            return data_path(path)

    else:
        raise IOError()
