import ssl
import socket

from gzip import GzipFile

try:
    from StringIO import StringIO
    from urllib2 import URLError
    from urllib2 import HTTPSHandler, BaseHandler, AbstractHTTPHandler, Request, addinfourl
    from httplib import HTTPException, HTTPConnection, HTTPS_PORT
except ImportError:
    from io import StringIO
    from urllib.error import URLError
    from urllib.request import HTTPSHandler, BaseHandler, AbstractHTTPHandler, Request, addinfourl
    from http.client import HTTPException, HTTPConnection, HTTPS_PORT

import re

try:
    basestring
except NameError:
    basestring = str


MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}


# SSL-related code proudly copy-pasted from https://stackoverflow.com/questions/1087227/validate-ssl-certificates-with-python

class InvalidCertificateException(HTTPException, URLError):
    def __init__(self, host, cert, reason):
        HTTPException.__init__(self)
        self.host = host
        self.cert = cert
        self.reason = reason

    def __str__(self):
        return ('Host %s returned an invalid certificate (%s) %s\n' %
                (self.host, self.reason, self.cert))


class CertValidatingHTTPSConnection(HTTPConnection):
    default_port = HTTPS_PORT

    def __init__(self, host, port=None, key_file=None, cert_file=None,
                             ca_certs=None, strict=None, **kwargs):
        HTTPConnection.__init__(self, host, port, strict, **kwargs)
        self.key_file = key_file
        self.cert_file = cert_file
        self.ca_certs = ca_certs
        if self.ca_certs:
            self.cert_reqs = ssl.CERT_REQUIRED
        else:
            self.cert_reqs = ssl.CERT_NONE

    def _GetValidHostsForCert(self, cert):
        if 'subjectAltName' in cert:
            return [x[1] for x in cert['subjectAltName']
                         if x[0].lower() == 'dns']
        else:
            return [x[0][1] for x in cert['subject']
                            if x[0][0].lower() == 'commonname']

    def _ValidateCertificateHostname(self, cert, hostname):
        hosts = self._GetValidHostsForCert(cert)
        for host in hosts:
            host_re = host.replace('.', '\.').replace('*', '[^.]*')
            if re.search('^%s$' % (host_re,), hostname, re.I):
                return True
        return False

    def connect(self):
        sock = socket.create_connection((self.host, self.port))
        self.sock = ssl.wrap_socket(sock, keyfile=self.key_file,
                                          certfile=self.cert_file,
                                          cert_reqs=self.cert_reqs,
                                          ca_certs=self.ca_certs)
        if self.cert_reqs & ssl.CERT_REQUIRED:
            cert = self.sock.getpeercert()
            hostname = self.host.split(':', 0)[0]
            if not self._ValidateCertificateHostname(cert, hostname):
                raise InvalidCertificateException(hostname, cert,
                                                  'hostname mismatch')


class VerifiedHTTPSHandler(HTTPSHandler):
    def __init__(self, **kwargs):
        AbstractHTTPHandler.__init__(self)
        self._connection_args = kwargs

    def https_open(self, req):
        def http_class_wrapper(host, **kwargs):
            full_kwargs = dict(self._connection_args)
            full_kwargs.update(kwargs)
            return CertValidatingHTTPSConnection(host, **full_kwargs)

        try:
            return self.do_open(http_class_wrapper, req)
        except URLError as e:
            if type(e.reason) == ssl.SSLError and e.reason.args[0] == 1:
                raise InvalidCertificateException(req.host, '',
                                                  e.reason.args[1])
            raise

    https_request = HTTPSHandler.do_request_

# end of copy-paste code


class GZIPHandler(BaseHandler):
    def http_request(self, req):
        req.add_unredirected_header('Accept-Encoding', 'gzip')
        return req

    def http_response(self, req, resp):
        if 200 <= resp.code < 300:
            if resp.headers.get('Content-Encoding') == 'gzip':
                data = resp.read()
                data = GzipFile(fileobj=StringIO(data), mode='r').read()

                fp = StringIO(data)
                old_resp = resp
                resp = addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
                resp.msg = old_resp.msg

        return resp

    https_response = http_response
    https_request = http_request


def detect_encoding(data, con=None):
    if con is not None and con.info().get('charset'):
        return con.info().get('charset')

    match = re.search('charset=["\']?([0-9a-zA-Z-]+)', data[:1000])
    if match:
        return match.groups()[0]

    match = re.search('encoding=["\']?([0-9a-zA-Z-]+)', data[:100])
    if match:
        return match.groups()[0].lower()

    return None


class EncodingFixHandler(BaseHandler):
    def http_response(self, req, resp):
        maintype = resp.info().get('Content-Type', '').split('/')[0]
        if 200 <= resp.code < 300 and maintype == 'text':
            data = resp.read()
            enc = detect_encoding(data, resp)

            if enc:
                data = data.decode(enc, 'replace')
                data = data.encode(enc)

            fp = StringIO(data)
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
                match = re.search(r'(?i)<meta http-equiv=.refresh[^>]*?url=(http.*?)["\']', data)
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
                    fp = StringIO(data)
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
        resp = addinfourl(StringIO(self.cache), headers, req.get_full_url(), 200)
        return resp

    https_request = http_request
