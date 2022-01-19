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
import pickle
import random
import re
import sys
import time
import zlib
from cgi import parse_header
from collections import OrderedDict
from io import BytesIO, StringIO

import chardet

from .caching import default_cache

try:
    # python 2
    from urllib import quote

    from httplib import HTTPMessage
    from urllib2 import (BaseHandler, HTTPCookieProcessor, HTTPRedirectHandler,
                         Request, addinfourl, build_opener, parse_http_list,
                         parse_keqv_list)
    from urlparse import urlparse, urlunparse
except ImportError:
    # python 3
    from email import message_from_string
    from http.client import HTTPMessage
    from urllib.parse import quote, urlparse, urlunparse
    from urllib.request import (BaseHandler, HTTPCookieProcessor,
                                HTTPRedirectHandler, Request, addinfourl,
                                build_opener, parse_http_list, parse_keqv_list)

try:
    # python 2
    basestring
except NameError:
    # python 3
    basestring = unicode = str


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
        'data': data,
        'url': con.geturl(),
        'con': con,
        'contenttype': contenttype,
        'encoding': encoding
    }


def custom_opener(follow=None, policy=None, force_min=None, force_max=None):
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

    handlers = [
        #DebugHandler(),
        SizeLimitHandler(500*1024), # 500KiB
        HTTPCookieProcessor(),
        GZIPHandler(),
        HTTPAllRedirectHandler(),
        HTTPEquivHandler(),
        HTTPRefreshHandler(),
        UAHandler(random.choice(DEFAULT_UAS)),
        BrowserlyHeaderHandler(),
        EncodingFixHandler(),
    ]

    if follow:
        handlers.append(AlternateHandler(MIMETYPE[follow]))

    handlers.append(CacheHandler(policy=policy, force_min=force_min, force_max=force_max))

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


class HTTPAllRedirectHandler(HTTPRedirectHandler):
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, 301, msg, headers)


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


def parse_headers(text=u'\n\n'):
    if sys.version_info[0] >= 3:
        # python 3
        return message_from_string(text, _class=HTTPMessage)

    else:
        # python 2
        return HTTPMessage(StringIO(text))


def error_response(code, msg, url=''):
    # return an error as a response
    resp = addinfourl(BytesIO(), parse_headers(), url, code)
    resp.msg = msg
    return resp


class CacheHandler(BaseHandler):
    " Cache based on etags/last-modified "

    privacy = 'private' # Websites can indicate whether the page should be cached
                        # by CDNs (e.g. shouldn't be the case for
                        # private/confidential/user-specific pages. With this
                        # setting, decide whether you want the cache to behave
                        # like a CDN (i.e. don't cache private pages, 'public'),
                        # or to behave like a end-user private pages
                        # ('private'). If unsure, 'public' is the safest bet,
                        # but many websites abuse this feature...

                      # NB. This overrides all the other min/max/policy settings.
    handler_order = 499

    def __init__(self, cache=None, force_min=None, force_max=None, policy=None):
        self.cache = cache or default_cache
        self.force_min = force_min
        self.force_max = force_max
        self.policy = policy # can be cached/refresh/offline/None (default)

        # Servers indicate how long they think their content is "valid". With
        # this parameter (force_min/max, expressed in seconds), we can override
        # the validity period (i.e. bypassing http headers)
        # Special choices, via "policy":
        #   cached: use the cache no matter what (and fetch the page online if
        #           not present in cache)
        #   refresh: valid zero second, i.e. force refresh
        #   offline: same as cached, i.e. use the cache no matter what, but do
        #            NOT fetch the page online if not present in cache, throw an
        #            error instead
        #   None: just follow protocols

        # sanity checks
        assert self.force_max is None or self.force_max >= 0
        assert self.force_min is None or self.force_min >= 0
        assert self.force_max is None or self.force_min is None or self.force_max >= self.force_min

    def load(self, url):
        try:
            data = pickle.loads(self.cache[url])

        except KeyError:
            data = None

        else:
            data['headers'] = parse_headers(data['headers'] or unicode())

        return data

    def save(self, key, data):
        data['headers'] = unicode(data['headers'])
        self.cache[key] = pickle.dumps(data, 0)

    def cached_response(self, req, fallback=None):
        req.from_morss_cache = True

        data = self.load(req.get_full_url())

        if data is not None:
            # return the cache as a response
            resp = addinfourl(BytesIO(data['data']), data['headers'], req.get_full_url(), data['code'])
            resp.msg = data['msg']
            return resp

        else:
            return fallback

    def save_response(self, req, resp):
        if req.from_morss_cache:
            # do not re-save (would reset the timing)
            return resp

        data = resp.read()

        self.save(req.get_full_url(), {
            'code': resp.code,
            'msg': resp.msg,
            'headers': resp.headers,
            'data': data,
            'timestamp': time.time()
            })

        fp = BytesIO(data)
        old_resp = resp
        resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
        resp.msg = old_resp.msg

        return resp

    def http_request(self, req):
        req.from_morss_cache = False # to track whether it comes from cache

        data = self.load(req.get_full_url())

        if data is not None:
            if 'etag' in data['headers']:
                req.add_unredirected_header('If-None-Match', data['headers']['etag'])

            if 'last-modified' in data['headers']:
                req.add_unredirected_header('If-Modified-Since', data['headers']['last-modified'])

        return req

    def http_open(self, req):
        # Reminder of how/when this function is called by urllib2:
        # If 'None' is returned, try your chance with the next-available handler
        # If a 'resp' is returned, stop there, and proceed with 'http_response'

        # Here, we try to see whether we want to use data from cache (i.e.
        # return 'resp'), or whether we want to refresh the content (return
        # 'None')

        data = self.load(req.get_full_url())

        if data is not None:
            # some info needed to process everything
            cache_control = parse_http_list(data['headers'].get('cache-control', ()))
            cache_control += parse_http_list(data['headers'].get('pragma', ()))

            cc_list = [x for x in cache_control if '=' not in x]
            cc_values = parse_keqv_list([x for x in cache_control if '=' in x])

            cache_age = time.time() - data['timestamp']

        # list in a simple way what to do in special cases

        if data is not None and 'private' in cc_list and self.privacy == 'public':
            # private data but public cache, do not use cache
            # privacy concern, so handled first and foremost
            # (and doesn't need to be addressed anymore afterwards)
            return None

        elif self.policy == 'offline':
            # use cache, or return an error
            return self.cached_response(
                req,
                error_response(409, 'Conflict', req.get_full_url())
            )

        elif self.policy == 'cached':
            # use cache, or fetch online
            return self.cached_response(req, None)

        elif self.policy == 'refresh':
            # force refresh
            return None

        elif data is None:
            # we have already settled all the cases that don't need the cache.
            # all the following ones need the cached item
            return None

        elif self.force_max is not None and cache_age > self.force_max:
            # older than we want, refresh
            return None

        elif self.force_min is not None and cache_age < self.force_min:
            # recent enough, use cache
            return self.cached_response(req)

        elif data['code'] == 301 and cache_age < 7*24*3600:
            # "301 Moved Permanently" has to be cached...as long as we want
            # (awesome HTTP specs), let's say a week (why not?). Use force_min=0
            # if you want to bypass this (needed for a proper refresh)
            return self.cached_response(req)

        elif self.force_min is None and ('no-cache' in cc_list or 'no-store' in cc_list):
            # kindly follow web servers indications, refresh if the same
            # settings are used all along, this section shouldn't be of any use,
            # since the page woudln't be cached in the first place the check is
            # only performed "just in case"
            # NB. NOT respected if force_min is set
            return None

        elif 'max-age' in cc_values and int(cc_values['max-age']) > cache_age:
            # server says it's still fine (and we trust him, if not, use overrides), use cache
            return self.cached_response(req)

        else:
            # according to the www, we have to refresh when nothing is said
            return None

    def http_response(self, req, resp):
        # code for after-fetch, to know whether to save to hard-drive (if sticking to http headers' will)

        if resp.code == 304 and resp.url in self.cache:
            # we are hopefully the first after the HTTP handler, so no need
            # to re-run all the *_response
            # here: cached page, returning from cache
            return self.cached_response(req)

        elif self.force_min is None and ('cache-control' in resp.headers or 'pragma' in resp.headers):
            cache_control = parse_http_list(resp.headers.get('cache-control', ()))
            cache_control += parse_http_list(resp.headers.get('pragma', ()))

            cc_list = [x for x in cache_control if '=' not in x]

            if 'no-cache' in cc_list or 'no-store' in cc_list or ('private' in cc_list and self.privacy == 'public'):
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


if 'IGNORE_SSL' in os.environ:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context


if __name__ == '__main__':
    req = adv_get(sys.argv[1] if len(sys.argv) > 1 else 'https://morss.it')

    if sys.flags.interactive:
        print('>>> Interactive shell: try using `req`')

    else:
        print(req['data'].decode(req['encoding']))
