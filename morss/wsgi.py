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

import cgitb
import mimetypes
import os.path
import re
import sys
import wsgiref.handlers
import wsgiref.simple_server
import wsgiref.util

import lxml.etree

try:
    # python 2
    from urllib import unquote
except ImportError:
    # python 3
    from urllib.parse import unquote

from . import caching, crawler, readabilite
from .morss import (DELAY, TIMEOUT, FeedFetch, FeedFormat, FeedGather,
                    MorssException, Options, log)
from .util import data_path

PORT = int(os.getenv('PORT', 8000))


def parse_options(options):
    """ Turns ['md=True'] into {'md':True} """
    out = {}

    for option in options:
        split = option.split('=', 1)

        if len(split) > 1:
            out[split[0]] = unquote(split[1]).replace('|', '/') # | -> / for backward compatibility (and Apache)

        else:
            out[split[0]] = True

    return out


def request_uri(environ):
    if 'REQUEST_URI' in environ:
        # when running on Apache/uwsgi
        url = environ['REQUEST_URI']

    elif 'RAW_URI' in environ:
        # gunicorn
        url = environ['RAW_URI']

    else:
        # when using other servers
        url = environ['PATH_INFO']

        if environ['QUERY_STRING']:
            url += '?' + environ['QUERY_STRING']

    return url


def cgi_parse_environ(environ):
    # get options

    url = request_uri(environ)[1:]
    url = re.sub(r'^(cgi/)?(morss.py|main.py)/', '', url)

    if url.startswith(':'):
        parts = url.split('/', 1)
        raw_options = parts[0].split(':')[1:]
        url = parts[1] if len(parts) > 1 else ''

    else:
        raw_options = []

    # init
    options = Options(parse_options(raw_options))

    return (url, options)


def cgi_app(environ, start_response):
    url, options = cgi_parse_environ(environ)

    headers = {}

    # headers
    headers['status'] = '200 OK'
    headers['cache-control'] = 'max-age=%s' % DELAY
    headers['x-content-type-options'] = 'nosniff' # safari work around

    if options.cors:
        headers['access-control-allow-origin'] = '*'

    if options.format == 'html':
        headers['content-type'] = 'text/html'
    elif options.txt or options.silent:
        headers['content-type'] = 'text/plain'
    elif options.format == 'json':
        headers['content-type'] = 'application/json'
    elif options.callback:
        headers['content-type'] = 'application/javascript'
    elif options.format == 'csv':
        headers['content-type'] = 'text/csv'
        headers['content-disposition'] = 'attachment; filename="feed.csv"'
    else:
        headers['content-type'] = 'text/xml'

    headers['content-type'] += '; charset=utf-8'

    # get the work done
    url, rss = FeedFetch(url, options)

    start_response(headers['status'], list(headers.items()))

    rss = FeedGather(rss, url, options)
    out = FeedFormat(rss, options)

    if options.silent:
        return ['']

    else:
        return [out]


def middleware(func):
    " Decorator to turn a function into a wsgi middleware "
    # This is called when parsing the "@middleware" code

    def app_builder(app):
        # This is called when doing app = cgi_wrapper(app)

        def app_wrap(environ, start_response):
            # This is called when a http request is being processed

            return func(environ, start_response, app)

        return app_wrap

    return app_builder


@middleware
def cgi_file_handler(environ, start_response, app):
    " Simple HTTP server to serve static files (.html, .css, etc.) "

    url = request_uri(environ)[1:]

    if url == '':
        url = 'index.html'

    if re.match(r'^/?([a-zA-Z0-9_-][a-zA-Z0-9\._-]+/?)*$', url):
        # if it is a legitimate url (no funny relative paths)
        try:
            path = data_path('www', url)
            f = open(path, 'rb')

        except IOError:
            # problem with file (cannot open or not found)
            pass

        else:
            # file successfully open
            headers = {}
            headers['status'] = '200 OK'
            headers['content-type'] = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            start_response(headers['status'], list(headers.items()))
            return wsgiref.util.FileWrapper(f)

    # regex didn't validate or no file found
    return app(environ, start_response)


def cgi_get(environ, start_response):
    url, options = cgi_parse_environ(environ)

    # get page
    if options['get'] in ('page', 'article'):
        req = crawler.adv_get(url=url, timeout=TIMEOUT)

        if req['contenttype'] in crawler.MIMETYPE['html']:
            if options['get'] == 'page':
                html = readabilite.parse(req['data'], encoding=req['encoding'])
                html.make_links_absolute(req['url'])

                kill_tags = ['script', 'iframe', 'noscript']

                for tag in kill_tags:
                    for elem in html.xpath('//'+tag):
                        elem.getparent().remove(elem)

                output = lxml.etree.tostring(html.getroottree(), encoding='utf-8', method='html')

            else: # i.e. options['get'] == 'article'
                output = readabilite.get_article(req['data'], url=req['url'], encoding_in=req['encoding'], encoding_out='utf-8', debug=options.debug)

        elif req['contenttype'] in crawler.MIMETYPE['xml'] + crawler.MIMETYPE['rss'] + crawler.MIMETYPE['json']:
            output = req['data']

        else:
            raise MorssException('unsupported mimetype')

    else:
        raise MorssException('no :get option passed')

    # return html page
    headers = {'status': '200 OK', 'content-type': req['contenttype'], 'X-Frame-Options': 'SAMEORIGIN'} # SAMEORIGIN to avoid potential abuse
    start_response(headers['status'], list(headers.items()))
    return [output]


dispatch_table = {
    'get': cgi_get,
    }


@middleware
def cgi_dispatcher(environ, start_response, app):
    url, options = cgi_parse_environ(environ)

    for key in dispatch_table.keys():
        if key in options:
            return dispatch_table[key](environ, start_response)

    return app(environ, start_response)


@middleware
def cgi_error_handler(environ, start_response, app):
    try:
        return app(environ, start_response)

    except (KeyboardInterrupt, SystemExit):
        raise

    except Exception as e:
        headers = {'status': '404 Not Found', 'content-type': 'text/html', 'x-morss-error': repr(e)}
        start_response(headers['status'], list(headers.items()), sys.exc_info())
        log('ERROR: %s' % repr(e))
        return [cgitb.html(sys.exc_info())]


@middleware
def cgi_encode(environ, start_response, app):
    out = app(environ, start_response)
    return [x if isinstance(x, bytes) else str(x).encode('utf-8') for x in out]


application = cgi_app
application = cgi_file_handler(application)
application = cgi_dispatcher(application)
application = cgi_error_handler(application)
application = cgi_encode(application)


def cgi_handle_request():
    app = cgi_app
    app = cgi_dispatcher(app)
    app = cgi_error_handler(app)
    app = cgi_encode(app)

    wsgiref.handlers.CGIHandler().run(app)


class WSGIRequestHandlerRequestUri(wsgiref.simple_server.WSGIRequestHandler):
    def get_environ(self):
        env = wsgiref.simple_server.WSGIRequestHandler.get_environ(self)
        env['REQUEST_URI'] = self.path
        return env


def cgi_start_server():
    caching.default_cache.autotrim()

    print('Serving http://localhost:%s/' % PORT)
    httpd = wsgiref.simple_server.make_server('', PORT, application, handler_class=WSGIRequestHandlerRequestUri)
    httpd.serve_forever()


if 'gunicorn' in os.getenv('SERVER_SOFTWARE', ''):
    caching.default_cache.autotrim()
