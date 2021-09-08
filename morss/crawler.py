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
import random
import re
import sys
import threading
import time
import zlib
from cgi import parse_header
from collections import OrderedDict
from io import BytesIO, StringIO

import chardet

try:
    # python 2
    from urllib import quote

    import mimetools
    from urllib2 import (BaseHandler, HTTPCookieProcessor, Request, addinfourl,
                         build_opener, parse_http_list, parse_keqv_list)
    from urlparse import urlparse, urlunparse
except ImportError:
    # python 3
    import email
    from urllib.parse import quote, urlparse, urlunparse
    from urllib.request import (BaseHandler, HTTPCookieProcessor, Request,
                                addinfourl, build_opener, parse_http_list,
                                parse_keqv_list)

try:
    # python 2
    basestring
except NameError:
    # python 3
    basestring = unicode = str


CACHE_SIZE = int(os.getenv('CACHE_SIZE', 1000)) # max number of items in cache (default: 1k items)
CACHE_LIFESPAN = int(os.getenv('CACHE_LIFESPAN', 60)) # how often to auto-clear the cache (default: 1min)


MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml', 'application/xhtml+xml'],
    'rss': ['application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}


DEFAULT_UAS = [
    #https://gist.github.com/fijimunkii/952acac988f2d25bef7e0284bc63c406
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:67.0) Gecko/20100101 Firefox/67.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36"
    ]


PROTOCOL = ['http', 'https']


def get(*args, **kwargs):
    return adv_get(*args, **kwargs)['data']


def adv_get(url, post=None, timeout=None, *args, **kwargs):
    url = sanitize_url(url)

    if post is not None:
        post = post.encode('utf-8')

    if timeout is None:
        con = custom_opener(*args, **kwargs).open(url, data=post)

    else:
        con = custom_opener(*args, **kwargs).open(url, data=post, timeout=timeout)

    data = con.read()

    contenttype = con.info().get('Content-Type', '').split(';')[0]
    encoding= detect_encoding(data, con)

    return {
        'data':data,
        'url': con.geturl(),
        'con': con,
        'contenttype': contenttype,
        'encoding': encoding
    }


def custom_opener(follow=None, delay=None):
    handlers = []

    # as per urllib2 source code, these Handelers are added first
    # *unless* one of the custom handlers inherits from one of them
    #
    # [ProxyHandler, UnknownHandler, HTTPHandler,
    # HTTPDefaultErrorHandler, HTTPRedirectHandler,
    # FTPHandler, FileHandler, HTTPErrorProcessor]
    # & HTTPSHandler
    #
    # when processing a request:
    # (1) all the *_request are run
    # (2) the *_open are run until sth is returned (other than None)
    # (3) all the *_response are run
    #
    # During (3), if an http error occurs (i.e. not a 2XX response code), the
    # http_error_* are run until sth is returned (other than None). If they all
    # return nothing, a python error is raised

    #handlers.append(DebugHandler())
    handlers.append(SizeLimitHandler(500*1024)) # 500KiB
    handlers.append(HTTPCookieProcessor())
    handlers.append(GZIPHandler())
    handlers.append(HTTPEquivHandler())
    handlers.append(HTTPRefreshHandler())
    handlers.append(UAHandler(random.choice(DEFAULT_UAS)))
    handlers.append(BrowserlyHeaderHandler())
    handlers.append(EncodingFixHandler())

    if follow:
        handlers.append(AlternateHandler(MIMETYPE[follow]))

    handlers.append(CacheHandler(force_min=delay))

    return build_opener(*handlers)


def is_ascii(string):
    # there's a native function in py3, but home-made fix for backward compatibility
    try:
        string.encode('ascii')

    except UnicodeError:
        return False

    else:
        return True


def sanitize_url(url):
    # make sure the url is unicode, i.e. not bytes
    if isinstance(url, bytes):
        url = url.decode()

    # make sure there's a protocol (http://)
    if url.split(':', 1)[0] not in PROTOCOL:
        url = 'http://' + url

    # turns out some websites have really badly fomatted urls (fix http:/badurl)
    url = re.sub('^(https?):/([^/])', r'\1://\2', url)

    # escape spaces
    url = url.replace(' ', '%20')

    # escape non-ascii unicode characters
    # https://stackoverflow.com/a/4391299
    parts = list(urlparse(url))

    for i in range(len(parts)):
        if not is_ascii(parts[i]):
            if i == 1:
                parts[i] = parts[i].encode('idna').decode('ascii')

            else:
                parts[i] = quote(parts[i].encode('utf-8'))

    return urlunparse(parts)


class RespDataHandler(BaseHandler):
    " Make it easier to use the reponse body "

    def data_reponse(self, req, resp, data):
        pass

    def http_response(self, req, resp):
        # read data
        data = resp.read()

        # process data and use returned content (if any)
        data = self.data_response(req, resp, data) or data

        # reformat the stuff
        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    https_response = http_response


class RespStrHandler(RespDataHandler):
    " Make it easier to use the _decoded_ reponse body "

    def str_reponse(self, req, resp, data_str):
        pass

    def data_response(self, req, resp, data):
        #decode
        enc = detect_encoding(data, resp)
        data_str = data.decode(enc, 'replace')

        #process
        data_str = self.str_response(req, resp, data_str)

        # return
        data = data_str.encode(enc) if data_str is not None else data

        #return
        return data


class DebugHandler(BaseHandler):
    handler_order = 2000

    def http_request(self, req):
        print(repr(req.header_items()))
        return req

    def http_response(self, req, resp):
        print(resp.headers.__dict__)
        return resp

    https_request = http_request
    https_response = http_response


class SizeLimitHandler(BaseHandler):
    """ Limit file size, defaults to 5MiB """

    handler_order = 450

    def __init__(self, limit=5*1024**2):
        self.limit = limit

    def http_response(self, req, resp):
        data = resp.read(self.limit)

        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    https_response = http_response


def UnGzip(data):
    " Supports truncated files "
    return zlib.decompressobj(zlib.MAX_WBITS | 32).decompress(data)


class GZIPHandler(RespDataHandler):
    def http_request(self, req):
        req.add_unredirected_header('Accept-Encoding', 'gzip')
        return req

    def data_response(self, req, resp, data):
        if 200 <= resp.code < 300:
            if resp.headers.get('Content-Encoding') == 'gzip':
                resp.headers['Content-Encoding'] = 'identity'

                return UnGzip(data)


def detect_encoding(data, resp=None):
    enc = detect_raw_encoding(data, resp)

    if enc.lower() == 'gb2312':
        enc = 'gbk'

    return enc


def detect_raw_encoding(data, resp=None):
    if resp is not None:
        enc = resp.headers.get('charset')
        if enc is not None:
            return enc

        enc = parse_header(resp.headers.get('content-type', ''))[1].get('charset')
        if enc is not None:
            return enc

    match = re.search(b'charset=["\']?([0-9a-zA-Z-]+)', data[:1000])
    if match:
        return match.groups()[0].lower().decode()

    match = re.search(b'encoding=["\']?([0-9a-zA-Z-]+)', data[:1000])
    if match:
        return match.groups()[0].lower().decode()

    enc = chardet.detect(data[-2000:])['encoding']
    if enc and enc != 'ascii':
        return enc

    return 'utf-8'


class EncodingFixHandler(RespStrHandler):
    def str_response(self, req, resp, data_str):
        return data_str


class UAHandler(BaseHandler):
    def __init__(self, useragent=None):
        self.useragent = useragent

    def http_request(self, req):
        if self.useragent:
            req.add_unredirected_header('User-Agent', self.useragent)
        return req

    https_request = http_request


class BrowserlyHeaderHandler(BaseHandler):
    """ Add more headers to look less suspicious """

    def http_request(self, req):
        req.add_unredirected_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
        req.add_unredirected_header('Accept-Language', 'en-US,en;q=0.5')
        return req

    https_request = http_request


def iter_html_tag(html_str, tag_name):
    " To avoid parsing whole pages when looking for a simple tag "

    re_tag = r'<%s(\s*[^>])*>' % tag_name
    re_attr = r'(?P<key>[^=\s]+)=[\'"](?P<value>[^\'"]+)[\'"]'

    for tag_match in re.finditer(re_tag, html_str):
        attr_match = re.findall(re_attr, tag_match.group(0))

        if attr_match is not None:
            yield dict(attr_match)


class AlternateHandler(RespStrHandler):
    " Follow <link rel='alternate' type='application/rss+xml' href='...' /> "

    def __init__(self, follow=None):
        self.follow = follow or []

    def str_response(self, req, resp, data_str):
        contenttype = resp.info().get('Content-Type', '').split(';')[0]

        if 200 <= resp.code < 300 and len(self.follow) and contenttype in MIMETYPE['html'] and contenttype not in self.follow:
            # opps, not what we were looking for, let's see if the html page suggests an alternative page of the right types

            for link in iter_html_tag(data_str[:10000], 'link'):
                if (link.get('rel') == 'alternate'
                        and link.get('type') in self.follow
                        and 'href' in link):
                    resp.code = 302
                    resp.msg = 'Moved Temporarily'
                    resp.headers['location'] = link.get('href')
                    break


class HTTPEquivHandler(RespStrHandler):
    " Handler to support <meta http-equiv='...' content='...' />, since it defines HTTP headers "

    handler_order = 600

    def str_response(self, req, resp, data_str):
        contenttype = resp.info().get('Content-Type', '').split(';')[0]
        if 200 <= resp.code < 300 and contenttype in MIMETYPE['html']:

            for meta in iter_html_tag(data_str[:10000], 'meta'):
                if 'http-equiv' in meta and 'content' in meta:
                    resp.headers[meta.get('http-equiv').lower()] = meta.get('content')


class HTTPRefreshHandler(BaseHandler):
    handler_order = 700 # HTTPErrorProcessor has a handler_order of 1000

    def http_response(self, req, resp):
        if 200 <= resp.code < 300:
            if resp.headers.get('refresh'):
                regex = r'(?i)^(?P<delay>[0-9]+)\s*;\s*url=(["\']?)(?P<url>.+)\2$'
                match = re.search(regex, resp.headers.get('refresh'))

                if match:
                    url = match.groupdict()['url']

                    if url:
                        resp.code = 302
                        resp.msg = 'Moved Temporarily'
                        resp.headers['location'] = url

        return resp

    https_response = http_response


class CacheHandler(BaseHandler):
    " Cache based on etags/last-modified "

    private_cache = False # Websites can indicate whether the page should be
                          # cached by CDNs (e.g. shouldn't be the case for
                          # private/confidential/user-specific pages.
                          # With this setting, decide whether (False) you want
                          # the cache to behave like a CDN (i.e. don't cache
                          # private pages), or (True) to behave like a end-cache
                          # private pages. If unsure, False is the safest bet.
    handler_order = 499

    def __init__(self, cache=None, force_min=None):
        self.cache = cache or default_cache
        self.force_min = force_min
            # Servers indicate how long they think their content is "valid".
            # With this parameter (force_min, expressed in seconds), we can
            # override the validity period (i.e. bypassing http headers)
            # Special values:
            #   -1: valid forever, i.e. use the cache no matter what (and fetch
            #       the page online if not present in cache)
            #    0: valid zero second, i.e. force refresh
            #   -2: same as -1, i.e. use the cache no matter what, but do NOT
            #       fetch the page online if not present in cache, throw an
            #       error instead

    def load(self, url):
        try:
            out = list(self.cache[url])
        except KeyError:
            out = [None, None, unicode(), bytes(), 0]

        if sys.version_info[0] >= 3:
            out[2] = email.message_from_string(out[2] or unicode()) # headers
        else:
            out[2] = mimetools.Message(StringIO(out[2] or unicode()))

        return out

    def save(self, url, code, msg, headers, data, timestamp):
        self.cache[url] = (code, msg, unicode(headers), data, timestamp)

    def is_cached(self, url):
        return self.load(url)[0] is not None

    def cached_response(self, req):
        # this does NOT check whether it's already cached, use with care
        (code, msg, headers, data, timestamp) = self.load(req.get_full_url())

        # return the cache as a response
        resp = addinfourl(BytesIO(data), headers, req.get_full_url(), code)
        resp.msg = msg

        return resp

    def save_response(self, req, resp):
        data = resp.read()

        self.save(req.get_full_url(), resp.code, resp.msg, resp.headers, data, time.time())

        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    def http_request(self, req):
        (code, msg, headers, data, timestamp) = self.load(req.get_full_url())

        if 'etag' in headers:
            req.add_unredirected_header('If-None-Match', headers['etag'])

        if 'last-modified' in headers:
            req.add_unredirected_header('If-Modified-Since', headers.get('last-modified'))

        return req

    def http_open(self, req):
        # Reminder of how/when this function is called by urllib2:
        # If 'None' is returned, try your chance with the next-available handler
        # If a 'resp' is returned, stop there, and proceed with 'http_response'

        (code, msg, headers, data, timestamp) = self.load(req.get_full_url())

        # some info needed to process everything
        cache_control = parse_http_list(headers.get('cache-control', ()))
        cache_control += parse_http_list(headers.get('pragma', ()))

        cc_list = [x for x in cache_control if '=' not in x]
        cc_values = parse_keqv_list([x for x in cache_control if '=' in x])

        cache_age = time.time() - timestamp

        # list in a simple way what to do when
        if self.force_min == -2:
            if code is not None:
                # already in cache, perfect, use cache
                return self.cached_response(req)

            else:
                # raise an error, via urllib handlers
                resp = addinfourl(BytesIO(), headers, req.get_full_url(), 409)
                resp.msg = 'Conflict'
                return resp

        elif code is None:
            # cache empty, refresh
            return None

        elif self.force_min == -1:
            # force use cache
            return self.cached_response(req)

        elif self.force_min == 0:
            # force refresh
            return None

        elif code == 301 and cache_age < 7*24*3600:
            # "301 Moved Permanently" has to be cached...as long as we want
            # (awesome HTTP specs), let's say a week (why not?). Use force_min=0
            # if you want to bypass this (needed for a proper refresh)
            return self.cached_response(req)

        elif (self.force_min is None or self.force_min > 0) and ('no-cache' in cc_list or 'no-store' in cc_list or ('private' in cc_list and not self.private_cache)):
            # kindly follow web servers indications, refresh
            # if the same settings are used all along, this section shouldn't be
            # of any use, since the page woudln't be cached in the first place
            # the check is only performed "just in case"
            return None

        elif 'max-age' in cc_values and int(cc_values['max-age']) > cache_age:
            # server says it's still fine (and we trust him, if not, use force_min=0), use cache
            return self.cached_response(req)

        elif self.force_min is not None and self.force_min > cache_age:
            # still recent enough for us, use cache
            return self.cached_response(req)

        else:
            # according to the www, we have to refresh when nothing is said
            return None

    def http_response(self, req, resp):
        # code for after-fetch, to know whether to save to hard-drive (if stiking to http headers' will)
        # NB. It might re-save requests pulled from cache, which will re-set the time() to the latest, i.e. lenghten its useful life

        if resp.code == 304 and self.is_cached(resp.url):
            # we are hopefully the first after the HTTP handler, so no need
            # to re-run all the *_response
            # here: cached page, returning from cache
            return self.cached_response(req)

        elif ('cache-control' in resp.headers or 'pragma' in resp.headers) and self.force_min is None:
            cache_control = parse_http_list(resp.headers.get('cache-control', ()))
            cache_control += parse_http_list(resp.headers.get('pragma', ()))

            cc_list = [x for x in cache_control if '=' not in x]

            if 'no-cache' in cc_list or 'no-store' in cc_list or ('private' in cc_list and not self.private_cache):
                # kindly follow web servers indications (do not save & return)
                return resp

            else:
                # save
                return self.save_response(req, resp)

        else:
            return self.save_response(req, resp)

    https_request = http_request
    https_open = http_open
    https_response = http_response


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


import sqlite3 # isort:skip


class SQLiteCache(BaseCache):
    def __init__(self, filename=':memory:'):
        self.con = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)

        with self.con:
            self.con.execute('CREATE TABLE IF NOT EXISTS data (url UNICODE PRIMARY KEY, code INT, msg UNICODE, headers UNICODE, data BLOB, timestamp INT)')
            self.con.execute('pragma journal_mode=WAL')

        self.trim()

    def __del__(self):
        self.con.close()

    def trim(self):
        with self.con:
            self.con.execute('DELETE FROM data WHERE timestamp <= ( SELECT timestamp FROM ( SELECT timestamp FROM data ORDER BY timestamp DESC LIMIT 1 OFFSET ? ) foo )', (CACHE_SIZE,))

    def __getitem__(self, url):
        row = self.con.execute('SELECT * FROM data WHERE url=?', (url,)).fetchone()

        if not row:
            raise KeyError

        return row[1:]

    def __setitem__(self, url, value): # value = (code, msg, headers, data, timestamp)
        value = list(value)
        value[3] = sqlite3.Binary(value[3]) # data
        value = tuple(value)

        with self.con:
            self.con.execute('INSERT INTO data VALUES (?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET code=?, msg=?, headers=?, data=?, timestamp=?', (url,) + value + value)


import pymysql.cursors # isort:skip


class MySQLCacheHandler(BaseCache):
    def __init__(self, user, password, database, host='localhost'):
        self.user = user
        self.password = password
        self.database = database
        self.host = host

        with self.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS data (url VARCHAR(255) NOT NULL PRIMARY KEY, code INT, msg TEXT, headers TEXT, data BLOB, timestamp INT)')

        self.trim()

    def cursor(self):
        return pymysql.connect(host=self.host, user=self.user, password=self.password, database=self.database, charset='utf8', autocommit=True).cursor()

    def trim(self):
        with self.cursor() as cursor:
            cursor.execute('DELETE FROM data WHERE timestamp <= ( SELECT timestamp FROM ( SELECT timestamp FROM data ORDER BY timestamp DESC LIMIT 1 OFFSET %s ) foo )', (CACHE_SIZE,))

    def __getitem__(self, url):
        cursor = self.cursor()
        cursor.execute('SELECT * FROM data WHERE url=%s', (url,))
        row = cursor.fetchone()

        if not row:
            raise KeyError

        return row[1:]

    def __setitem__(self, url, value): # (code, msg, headers, data, timestamp)
        with self.cursor() as cursor:
            cursor.execute('INSERT INTO data VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE code=%s, msg=%s, headers=%s, data=%s, timestamp=%s',
                (url,) + value + value)


class CappedDict(OrderedDict, BaseCache):
    def trim(self):
        if CACHE_SIZE >= 0:
            for i in range( max( len(self) - CACHE_SIZE , 0 )):
                self.popitem(False)

    def __setitem__(self, key, value):
        # https://docs.python.org/2/library/collections.html#ordereddict-examples-and-recipes
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, value)


if 'CACHE' in os.environ:
    if os.environ['CACHE'] == 'mysql':
        default_cache = MySQLCacheHandler(
            user = os.getenv('MYSQL_USER'),
            password = os.getenv('MYSQL_PWD'),
            database = os.getenv('MYSQL_DB'),
            host = os.getenv('MYSQL_HOST', 'localhost')
        )

    elif os.environ['CACHE'] == 'sqlite':
        if 'SQLITE_PATH' in os.environ:
            path = os.getenv('SQLITE_PATH')

        else:
            path = ':memory:'

        default_cache = SQLiteCache(path)

else:
        default_cache = CappedDict()


if 'IGNORE_SSL' in os.environ:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context


if __name__ == '__main__':
    req = adv_get(sys.argv[1] if len(sys.argv) > 1 else 'https://morss.it')

    if sys.flags.interactive:
        print('>>> Interactive shell: try using `req`')

    else:
        print(req['data'].decode(req['encoding']))
