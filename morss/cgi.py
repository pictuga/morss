import sys
import os.path
import re
import lxml.etree

import cgitb

try:
    # python 2
    from urllib import unquote
except ImportError:
    # python 3
    from urllib.parse import unquote

from . import crawler
from . import readabilite
from .morss import FeedFetch, FeedGather, FeedFormat
from .morss import Options, log, TIMEOUT, DELAY, MorssException

from . import cred


def parse_options(options):
    """ Turns ['md=True'] into {'md':True} """
    out = {}

    for option in options:
        split = option.split('=', 1)

        if len(split) > 1:
            out[split[0]] = split[1]

        else:
            out[split[0]] = True

    return out


def cgi_parse_environ(environ):
    # get options

    if 'REQUEST_URI' in environ:
        # when running on Apache
        url = environ['REQUEST_URI'][1:]

    else:
        # when using internal server
        url = environ['PATH_INFO'][1:]

        if environ['QUERY_STRING']:
            url += '?' + environ['QUERY_STRING']

    url = re.sub(r'^/?(cgi/)?(morss.py|main.py)/', '', url)

    if url.startswith(':'):
        split = url.split('/', 1)

        raw_options = unquote(split[0]).replace('|', '/').replace('\\\'', '\'').split(':')[1:]

        if len(split) > 1:
            url = split[1]

        else:
            url = ''

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

    files = {
        '': 'text/html',
        'index.html': 'text/html',
        'sheet.xsl': 'text/xsl'}

    if 'REQUEST_URI' in environ:
        url = environ['REQUEST_URI'][1:]

    else:
        url = environ['PATH_INFO'][1:]

    if url in files:
        headers = {}

        if url == '':
            url = 'index.html'

        paths = [os.path.join(sys.prefix, 'share/morss/www', url),
            os.path.join(os.path.dirname(__file__), '../www', url)]

        for path in paths:
            try:
                body = open(path, 'rb').read()

                headers['status'] = '200 OK'
                headers['content-type'] = files[url]
                start_response(headers['status'], list(headers.items()))
                return [body]

            except IOError:
                continue

        else:
            # the for loop did not return, so here we are, i.e. no file found
            headers['status'] = '404 Not found'
            start_response(headers['status'], list(headers.items()))
            return ['Error %s' % headers['status']]

    else:
        return app(environ, start_response)


def cgi_get(environ, start_response):
    url, options = cgi_parse_environ(environ)

    # get page
    req = crawler.adv_get(url=url, timeout=TIMEOUT)

    if req['contenttype'] in ['text/html', 'application/xhtml+xml', 'application/xml']:
        if options.get == 'page':
            html = readabilite.parse(req['data'], encoding=req['encoding'])
            html.make_links_absolute(req['url'])

            kill_tags = ['script', 'iframe', 'noscript']

            for tag in kill_tags:
                for elem in html.xpath('//'+tag):
                    elem.getparent().remove(elem)

            output = lxml.etree.tostring(html.getroottree(), encoding='utf-8', method='html')

        elif options.get == 'article':
            output = readabilite.get_article(req['data'], url=req['url'], encoding_in=req['encoding'], encoding_out='utf-8', debug=options.debug)

        else:
            raise MorssException('no :get option passed')

    else:
        output = req['data']

    # return html page
    headers = {'status': '200 OK', 'content-type': 'text/html; charset=utf-8', 'X-Frame-Options': 'SAMEORIGIN'} # SAMEORIGIN to avoid potential abuse
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
        headers = {'status': '500 Oops', 'content-type': 'text/html'}
        start_response(headers['status'], list(headers.items()), sys.exc_info())
        log('ERROR: %s' % repr(e), force=True)
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
