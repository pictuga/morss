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

import os
import threading
import time
from collections import OrderedDict

CACHE_SIZE = int(os.getenv('CACHE_SIZE', 1000)) # max number of items in cache (default: 1k items)
CACHE_LIFESPAN = int(os.getenv('CACHE_LIFESPAN', 60)) # how often to auto-clear the cache (default: 1min)


class BaseCache:
    """ Subclasses must behave like a dict """

    def trim(self):
        pass

    def autotrim(self, delay=CACHE_LIFESPAN):
        # trim the cache every so often

        self.trim()

        t = threading.Timer(delay, self.autotrim)
        t.daemon = True
        t.start()

    def __contains__(self, url):
        try:
            self[url]

        except KeyError:
            return False

        else:
            return True


class CappedDict(OrderedDict, BaseCache):
    def trim(self):
        if CACHE_SIZE >= 0:
            for i in range( max( len(self) - CACHE_SIZE , 0 )):
                self.popitem(False)

    def __setitem__(self, key, data):
        # https://docs.python.org/2/library/collections.html#ordereddict-examples-and-recipes
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, data)


try:
    import redis # isort:skip
except ImportError:
    pass


class RedisCacheHandler(BaseCache):
    def __init__(self, host='localhost', port=6379, db=0, password=None):
        self.r = redis.Redis(host=host, port=port, db=db, password=password)

    def __getitem__(self, key):
        return self.r.get(key)

    def __setitem__(self, key, data):
        self.r.set(key, data)


try:
    import diskcache # isort:skip
except ImportError:
    pass


class DiskCacheHandler(BaseCache):
    def __init__(self, directory=None, **kwargs):
        self.cache = diskcache.Cache(directory=directory, eviction_policy='least-frequently-used', **kwargs)

    def __del__(self):
        self.cache.close()

    def trim(self):
        self.cache.cull()

    def __getitem__(self, key):
        return self.cache[key]

    def __setitem__(self, key, data):
        self.cache.set(key, data)


if 'CACHE' in os.environ:
    if os.environ['CACHE'] == 'mysql':
        default_cache = MySQLCacheHandler(
            user = os.getenv('MYSQL_USER'),
            password = os.getenv('MYSQL_PWD'),
            database = os.getenv('MYSQL_DB'),
            host = os.getenv('MYSQL_HOST', 'localhost')
        )

    elif os.environ['CACHE'] == 'sqlite':
        default_cache = SQLiteCache(
            os.getenv('SQLITE_PATH', ':memory:')
        )

    elif os.environ['CACHE'] == 'redis':
        default_cache = RedisCacheHandler(
            host = os.getenv('REDIS_HOST', 'localhost'),
            port = int(os.getenv('REDIS_PORT', 6379)),
            db = int(os.getenv('REDIS_DB', 0)),
            password = os.getenv('REDIS_PWD', None)
        )

    elif os.environ['CACHE'] == 'diskcache':
        default_cache = DiskCacheHandler(
            directory = os.getenv('DISKCACHE_DIR', '/tmp/morss-diskcache'),
            size_limit = CACHE_SIZE # in Bytes
        )

else:
        default_cache = CappedDict()
