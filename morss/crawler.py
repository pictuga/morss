import ssl
import socket

from gzip import GzipFile
from io import BytesIO

try:
    from urllib2 import BaseHandler, addinfourl, parse_keqv_list, parse_http_list
except ImportError:
    from urllib.request import BaseHandler, addinfourl, parse_keqv_list, parse_http_list

import re

try:
    basestring
except NameError:
    basestring = str


MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}

class GZIPHandler(BaseHandler):
    def http_request(self, req):
        req.add_unredirected_header('Accept-Encoding', 'gzip')
        return req

    def http_response(self, req, resp):
        if 200 <= resp.code < 300:
            if resp.headers.get('Content-Encoding') == 'gzip':
                data = resp.read()
                data = GzipFile(fileobj=BytesIO(data), mode='r').read()

                fp = BytesIO(data)
                old_resp = resp
                resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
                resp.msg = old_resp.msg

        return resp

    https_response = http_response
    https_request = http_request


def detect_encoding(data, con=None):
    if con is not None and con.info().get('charset'):
        return con.info().get('charset')

    match = re.search(b'charset=["\']?([0-9a-zA-Z-]+)', data[:1000])
    if match:
        return match.groups()[0].lower().decode()

    match = re.search(b'encoding=["\']?([0-9a-zA-Z-]+)', data[:100])
    if match:
        return match.groups()[0].lower().decode()

    return 'utf-8'


class EncodingFixHandler(BaseHandler):
    def http_response(self, req, resp):
        maintype = resp.info().get('Content-Type', '').split('/')[0]
        if 200 <= resp.code < 300 and maintype == 'text':
            data = resp.read()
            enc = detect_encoding(data, resp)

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
        if req.host != 'feeds.feedburner.com':
            req.add_unredirected_header('Referer', 'http://%s' % req.host)
        return req

    https_request = http_request


class ContentNegociationHandler(BaseHandler): #FIXME
    def __init__(self, accept=None, strict=False):
        self.accept = accept
        self.strict = strict

    def http_request(self, req):
        if self.accept is not None:
            if isinstance(self.accept, basestring):
                self.accept = (self.accept,)

            out = {}
            rank = 1.1
            for group in self.accept:
                rank -= 0.1

                if isinstance(group, basestring):
                    if group in MIMETYPE:
                        group = MIMETYPE[group]
                    else:
                        out[group] = rank
                        continue

                for mime in group:
                    if mime not in out:
                        out[mime] = rank

            if not self.strict:
                out['*/*'] = rank - 0.1

            string = ','.join([x + ';q={0:.1}'.format(out[x]) if out[x] != 1 else x for x in out])
            req.add_unredirected_header('Accept', string)

        return req

    https_request = http_request


class MetaRedirectHandler(BaseHandler):
    def http_response(self, req, resp):
        contenttype = resp.info().get('Content-Type', '').split(';')[0]
        if 200 <= resp.code < 300 and contenttype.startswith('text/'):
            if contenttype in MIMETYPE['html']:
                data = resp.read()
                match = re.search(b'(?i)<meta http-equiv=.refresh[^>]*?url=(http.*?)["\']', data)
                if match:
                    new_url = match.groups()[0]
                    new_headers = dict((k, v) for k, v in list(req.headers.items())
                                       if k.lower() not in ('content-length', 'content-type'))
                    new = Request(new_url,
                                          headers=new_headers,
                                          origin_req_host=req.get_origin_req_host(),
                                          unverifiable=True)

                    return self.parent.open(new, timeout=req.timeout)
                else:
                    fp = BytesIO(data)
                    old_resp = resp
                    resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
                    resp.msg = old_resp.msg

        return resp

    https_response = http_response


class EtagHandler(BaseHandler):
    def __init__(self, cache="", etag=None, lastmodified=None):
        self.cache = cache
        self.etag = etag
        self.lastmodified = lastmodified

    def http_request(self, req):
        if self.cache:
            if self.etag:
                req.add_unredirected_header('If-None-Match', self.etag)
            if self.lastmodified:
                req.add_unredirected_header('If-Modified-Since', self.lastmodified)

        return req

    def http_error_304(self, req, fp, code, msg, headers):
        if self.etag:
            headers.addheader('etag', self.etag)
        if self.lastmodified:
            headers.addheader('last-modified', self.lastmodified)
        resp = addinfourl(BytesIO(self.cache), headers, req.get_full_url(), 200)
        return resp

    https_request = http_request
