import sys

import ssl
import socket

from gzip import GzipFile
from io import BytesIO, StringIO
import re
import chardet
from cgi import parse_header
import lxml.html
import time

try:
    from urllib2 import BaseHandler, HTTPCookieProcessor, Request, addinfourl, parse_keqv_list, parse_http_list, build_opener
    import mimetools
except ImportError:
    from urllib.request import BaseHandler, HTTPCookieProcessor, Request, addinfourl, parse_keqv_list, parse_http_list, build_opener
    import email

try:
    basestring
except NameError:
    basestring = unicode = str


MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml', 'application/xhtml+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}


DEFAULT_UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:25.0) Gecko/20100101 Firefox/25.0'


def custom_handler(accept=None, strict=False, delay=None, encoding=None, basic=False):
    handlers = []

    # as per urllib2 source code, these Handelers are added first
    # *unless* one of the custom handlers inherits from one of them
    #
    # [ProxyHandler, UnknownHandler, HTTPHandler,
    # HTTPDefaultErrorHandler, HTTPRedirectHandler,
    # FTPHandler, FileHandler, HTTPErrorProcessor]
    # & HTTPSHandler

    #handlers.append(DebugHandler())
    handlers.append(SizeLimitHandler(500*1024)) # 500KiB
    handlers.append(HTTPCookieProcessor())
    handlers.append(GZIPHandler())
    handlers.append(HTTPEquivHandler())
    handlers.append(HTTPRefreshHandler())
    handlers.append(UAHandler(DEFAULT_UA))

    if not basic:
        handlers.append(AutoRefererHandler())

    handlers.append(EncodingFixHandler(encoding))

    if accept:
        handlers.append(ContentNegociationHandler(MIMETYPE[accept], strict))

    handlers.append(CacheHandler(force_min=delay))

    return build_opener(*handlers)


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

    def __init__(self, limit=5*1024^2):
        self.limit = limit

    def http_response(self, req, resp):
        data = resp.read(self.limit)

        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    https_response = http_response


def UnGzip(cprss, CHUNKSIZE=64*1024): # the bigger the CHUNKSIZE, the faster
    " Supports truncated files "
    gz = GzipFile(fileobj=cprss, mode='rb')

    data = b''
    chunk = gz.read(CHUNKSIZE)

    try:
        while chunk:
            data += chunk
            chunk = gz.read(CHUNKSIZE)

    except (IOError, EOFError):
        pass

    return data


class GZIPHandler(BaseHandler):
    def http_request(self, req):
        req.add_unredirected_header('Accept-Encoding', 'gzip')
        return req

    def http_response(self, req, resp):
        if 200 <= resp.code < 300:
            if resp.headers.get('Content-Encoding') == 'gzip':
                data = resp.read()

                data = UnGzip(BytesIO(data))

                resp.headers['Content-Encoding'] = 'identity'

                fp = BytesIO(data)
                old_resp = resp
                resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
                resp.msg = old_resp.msg

        return resp

    https_response = http_response
    https_request = http_request


def detect_encoding(data, resp=None):
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


class EncodingFixHandler(BaseHandler):
    def __init__(self, encoding=None):
        self.encoding = encoding

    def http_response(self, req, resp):
        maintype = resp.info().get('Content-Type', '').split('/')[0]
        if 200 <= resp.code < 300 and maintype == 'text':
            data = resp.read()

            if not self.encoding:
                enc = detect_encoding(data, resp)
            else:
                enc = self.encoding

            if enc:
                data = data.decode(enc, 'replace')
                data = data.encode(enc)

            fp = BytesIO(data)
            old_resp = resp
            resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
            resp.msg = old_resp.msg

        return resp

    https_response = http_response


class UAHandler(BaseHandler):
    def __init__(self, useragent=None):
        self.useragent = useragent

    def http_request(self, req):
        if self.useragent:
            req.add_unredirected_header('User-Agent', self.useragent)
        return req

    https_request = http_request


class AutoRefererHandler(BaseHandler):
    def http_request(self, req):
        req.add_unredirected_header('Referer', 'http://%s' % req.host)
        return req

    https_request = http_request


class ContentNegociationHandler(BaseHandler):
    " Handler for content negociation. Also parses <link rel='alternate' type='application/rss+xml' href='...' /> "

    def __init__(self, accept=None, strict=False):
        self.accept = accept
        self.strict = strict

    def http_request(self, req):
        if self.accept is not None:
            if isinstance(self.accept, basestring):
                self.accept = (self.accept,)

            string = ','.join(self.accept)

            if self.strict:
                string += ',*/*;q=0.9'

            req.add_unredirected_header('Accept', string)

        return req

    def http_response(self, req, resp):
        contenttype = resp.info().get('Content-Type', '').split(';')[0]
        if 200 <= resp.code < 300 and self.accept is not None and self.strict and contenttype in MIMETYPE['html'] and contenttype not in self.accept:
            # opps, not what we were looking for, let's see if the html page suggests an alternative page of the right types

            data = resp.read()
            links = lxml.html.fromstring(data[:10000]).findall('.//link[@rel="alternate"]')

            for link in links:
                if link.get('type', '') in self.accept:
                    resp.code = 302
                    resp.msg = 'Moved Temporarily'
                    resp.headers['location'] = link.get('href')

            fp = BytesIO(data)
            old_resp = resp
            resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
            resp.msg = old_resp.msg

        return resp

    https_request = http_request
    https_response = http_response


class HTTPEquivHandler(BaseHandler):
    " Handler to support <meta http-equiv='...' content='...' />, since it defines HTTP headers "

    handler_order = 600

    def http_response(self, req, resp):
        contenttype = resp.info().get('Content-Type', '').split(';')[0]
        if 200 <= resp.code < 300 and contenttype in MIMETYPE['html']:
            data = resp.read()

            headers = lxml.html.fromstring(data[:10000]).findall('.//meta[@http-equiv]')

            for header in headers:
                resp.headers[header.get('http-equiv').lower()] = header.get('content')

            fp = BytesIO(data)
            old_resp = resp
            resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
            resp.msg = old_resp.msg

        return resp

    https_response = http_response


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


default_cache = {}


class CacheHandler(BaseHandler):
    " Cache based on etags/last-modified "

    private_cache = False # False to behave like a CDN (or if you just don't care), True like a PC
    handler_order = 499

    def __init__(self, cache=None, force_min=None):
        self.cache = cache or default_cache
        self.force_min = force_min # force_min (seconds) to bypass http headers, -1 forever, 0 never, -2 do nothing if not in cache

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

    def http_request(self, req):
        (code, msg, headers, data, timestamp) = self.load(req.get_full_url())

        if 'etag' in headers:
            req.add_unredirected_header('If-None-Match', headers['etag'])

        if 'last-modified' in headers:
            req.add_unredirected_header('If-Modified-Since', headers.get('last-modified'))

        return req

    def http_open(self, req):
        (code, msg, headers, data, timestamp) = self.load(req.get_full_url())

        # some info needed to process everything
        cache_control = parse_http_list(headers.get('cache-control', ()))
        cache_control += parse_http_list(headers.get('pragma', ()))

        cc_list = [x for x in cache_control if '=' not in x]
        cc_values = parse_keqv_list([x for x in cache_control if '=' in x])

        cache_age = time.time() - timestamp

        # list in a simple way what to do when
        if req.get_header('Morss') == 'from_304': # for whatever reason, we need an uppercase
            # we're just in the middle of a dirty trick, use cache
            pass

        elif self.force_min == -2:
            if code is not None:
                # already in cache, perfect, use cache
                pass

            else:
                headers['Morss'] = 'from_cache'
                resp = addinfourl(BytesIO(), headers, req.get_full_url(), 409)
                resp.msg = 'Conflict'
                return resp

        elif code is None:
            # cache empty, refresh
            return None

        elif self.force_min == -1:
            # force use cache
            pass

        elif self.force_min == 0:
            # force refresh
            return None

        elif code == 301 and cache_age < 7*24*3600:
            # "301 Moved Permanently" has to be cached...as long as we want (awesome HTTP specs), let's say a week (why not?)
            # use force_min=0 if you want to bypass this (needed for a proper refresh)
            pass

        elif  self.force_min is None and ('no-cache' in cc_list
                                        or 'no-store' in cc_list
                                        or ('private' in cc_list and not self.private)):
            # kindly follow web servers indications, refresh
            return None

        elif 'max-age' in cc_values and int(cc_values['max-age']) > cache_age:
            # server says it's still fine (and we trust him, if not, use force_min=0), use cache
            pass

        elif self.force_min is not None and self.force_min > cache_age:
            # still recent enough for us, use cache
            pass

        else:
            # according to the www, we have to refresh when nothing is said
            return None

        # return the cache as a response
        headers['morss'] = 'from_cache' # TODO delete the morss header from incoming pages, to avoid websites messing up with us
        resp = addinfourl(BytesIO(data), headers, req.get_full_url(), code)
        resp.msg = msg

        return resp

    def http_response(self, req, resp):
        # code for after-fetch, to know whether to save to hard-drive (if stiking to http headers' will)

        if resp.code == 304:
            return resp

        if ('cache-control' in resp.headers or 'pragma' in resp.headers) and self.force_min is None:
            cache_control = parse_http_list(resp.headers.get('cache-control', ()))
            cache_control += parse_http_list(resp.headers.get('pragma', ()))

            cc_list = [x for x in cache_control if '=' not in x]

            if 'no-cache' in cc_list or 'no-store' in cc_list or ('private' in cc_list and not self.private):
                # kindly follow web servers indications
                return resp

        if resp.headers.get('Morss') == 'from_cache':
            # it comes from cache, so no need to save it again
            return resp

        # save to disk
        data = resp.read()
        self.save(req.get_full_url(), resp.code, resp.msg, resp.headers, data, time.time())

        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    def http_error_304(self, req, fp, code, msg, headers):
        cache = list(self.load(req.get_full_url()))

        if cache[0]:
            cache[-1] = time.time()
            self.save(req.get_full_url(), *cache)

            new = Request(req.get_full_url(),
                           headers=req.headers,
                           unverifiable=True)

            new.add_unredirected_header('Morss', 'from_304')

            return self.parent.open(new, timeout=req.timeout)

        return None

    https_request = http_request
    https_open = http_open
    https_response = http_response


class BaseCache:
    def __contains__(self, url):
        try:
            self[url]

        except KeyError:
            return False

        else:
            return True


import sqlite3


class SQLiteCache(BaseCache):
    def __init__(self, filename=':memory:'):
        self.con = sqlite3.connect(filename or sqlite_default, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)

        with self.con:
            self.con.execute('CREATE TABLE IF NOT EXISTS data (url UNICODE PRIMARY KEY, code INT, msg UNICODE, headers UNICODE, data BLOB, timestamp INT)')
            self.con.execute('pragma journal_mode=WAL')

    def __del__(self):
        self.con.close()

    def __getitem__(self, url):
        row = self.con.execute('SELECT * FROM data WHERE url=?', (url,)).fetchone()

        if not row:
            raise KeyError

        return row[1:]

    def __setitem__(self, url, value): # value = (code, msg, headers, data, timestamp)
        if url in self:
            with self.con:
                self.con.execute('UPDATE data SET code=?, msg=?, headers=?, data=?, timestamp=? WHERE url=?',
                    value + (url,))

        else:
            with self.con:
                self.con.execute('INSERT INTO data VALUES (?,?,?,?,?,?)', (url,) + value)


import pymysql.cursors


class MySQLCacheHandler(BaseCache):
    " NB. Requires mono-threading, as pymysql doesn't isn't thread-safe "
    def __init__(self, user, password, database, host='localhost'):
        self.con = pymysql.connect(host=host, user=user, password=password, database=database, charset='utf8', autocommit=True)

        with self.con.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS data (url VARCHAR(255) NOT NULL PRIMARY KEY, code INT, msg TEXT, headers TEXT, data BLOB, timestamp INT)')

    def __del__(self):
        self.con.close()

    def __getitem__(self, url):
        cursor = self.con.cursor()
        cursor.execute('SELECT * FROM data WHERE url=%s', (url,))
        row = cursor.fetchone()

        if not row:
            raise KeyError

        return row[1:]

    def __setitem__(self, url, value): # (code, msg, headers, data, timestamp)
        if url in self:
            with self.con.cursor() as cursor:
                cursor.execute('UPDATE data SET code=%s, msg=%s, headers=%s, data=%s, timestamp=%s WHERE url=%s',
                    value + (url,))

        else:
            with self.con.cursor() as cursor:
                cursor.execute('INSERT INTO data VALUES (%s,%s,%s,%s,%s,%s)', (url,) + value)
