import sys
import os
import os.path

import time
from datetime import datetime
from dateutil import tz

from fnmatch import fnmatch
import re

import lxml.etree
import lxml.html

from . import feeds
from . import crawler
from . import readabilite

import wsgiref.simple_server
import wsgiref.handlers
import cgitb


try:
    # python 2
    from httplib import HTTPException
    from urllib import unquote
    from urlparse import urlparse, urljoin, parse_qs
except ImportError:
    # python 3
    from http.client import HTTPException
    from urllib.parse import unquote
    from urllib.parse import urlparse, urljoin, parse_qs

MAX_ITEM = 5  # cache-only beyond
MAX_TIME = 2  # cache-only after (in sec)

LIM_ITEM = 10  # deletes what's beyond
LIM_TIME = 2.5  # deletes what's after

DELAY = 10 * 60  # xml cache & ETag cache (in sec)
TIMEOUT = 4  # http timeout (in sec)

DEBUG = False
PORT = 8080


def filterOptions(options):
    return options

    # example of filtering code below

    #allowed = ['proxy', 'clip', 'cache', 'force', 'silent', 'pro', 'debug']
    #filtered = dict([(key,value) for (key,value) in options.items() if key in allowed])

    #return filtered


class MorssException(Exception):
    pass


def log(txt, force=False):
    if DEBUG or force:
        if 'REQUEST_URI' in os.environ:
            open('morss.log', 'a').write("%s\n" % repr(txt))

        else:
            print(repr(txt))


def len_html(txt):
    if len(txt):
        return len(lxml.html.fromstring(txt).text_content())

    else:
        return 0


def count_words(txt):
    if len(txt):
        return len(lxml.html.fromstring(txt).text_content().split())

    return 0


class Options:
    def __init__(self, options=None, **args):
        if len(args):
            self.options = args
            self.options.update(options or {})

        else:
            self.options = options or {}

    def __getattr__(self, key):
        if key in self.options:
            return self.options[key]

        else:
            return False

    def __setitem__(self, key, value):
        self.options[key] = value

    def __contains__(self, key):
        return key in self.options


def parseOptions(options):
    """ Turns ['md=True'] into {'md':True} """
    out = {}

    for option in options:
        split = option.split('=', 1)

        if len(split) > 1:
            if split[0].lower() == 'true':
                out[split[0]] = True

            elif split[0].lower() == 'false':
                out[split[0]] = False

            else:
                out[split[0]] = split[1]

        else:
            out[split[0]] = True

    return out


def ItemFix(item, options, feedurl='/'):
    """ Improves feed items (absolute links, resolve feedburner links, etc) """

    # check unwanted uppercase title
    if item.title is not None and len(item.title) > 20 and item.title.isupper():
        item.title = item.title.title()

    # check if it includes link
    if not item.link:
        log('no link')
        return item

    # wikipedia daily highlight
    if fnmatch(feedurl, 'http*://*.wikipedia.org/w/api.php?*&feedformat=atom'):
        match = lxml.html.fromstring(item.desc).xpath('//b/a/@href')
        if len(match):
            item.link = match[0]
            log(item.link)

    # at user's election, use first <a>
    if options.firstlink and (item.desc or item.content):
        match = lxml.html.fromstring(item.desc or item.content).xpath('//a/@href')
        if len(match):
            item.link = match[0]
            log(item.link)

    # check relative urls
    item.link = urljoin(feedurl, item.link)

    # google translate
    if fnmatch(item.link, 'http://translate.google.*/translate*u=*'):
        item.link = parse_qs(urlparse(item.link).query)['u'][0]
        log(item.link)

    # google
    if fnmatch(item.link, 'http://www.google.*/url?q=*'):
        item.link = parse_qs(urlparse(item.link).query)['q'][0]
        log(item.link)

    # google news
    if fnmatch(item.link, 'http://news.google.com/news/url*url=*'):
        item.link = parse_qs(urlparse(item.link).query)['url'][0]
        log(item.link)

    # pocket
    if fnmatch(item.link, 'https://getpocket.com/redirect?url=*'):
        item.link = parse_qs(urlparse(item.link).query)['url'][0]
        log(item.link)

    # facebook
    if fnmatch(item.link, 'https://www.facebook.com/l.php?u=*'):
        item.link = parse_qs(urlparse(item.link).query)['u'][0]
        log(item.link)

    # feedburner FIXME only works if RSS...
    item.NSMAP['feedburner'] = 'http://rssnamespace.org/feedburner/ext/1.0'
    match = item.rule_str('feedburner:origLink')
    if match:
        item.link = match

    # feedsportal
    match = re.search('/([0-9a-zA-Z]{20,})/story01.htm$', item.link)
    if match:
        url = match.groups()[0].split('0')
        t = {'A': '0', 'B': '.', 'C': '/', 'D': '?', 'E': '-', 'F': '=',
             'G': '&', 'H': ',', 'I': '_', 'J': '%', 'K': '+', 'L': 'http://',
             'M': 'https://', 'N': '.com', 'O': '.co.uk', 'P': ';', 'Q': '|',
             'R': ':', 'S': 'www.', 'T': '#', 'U': '$', 'V': '~', 'W': '!',
             'X': '(', 'Y': ')', 'Z': 'Z'}
        item.link = ''.join([(t[s[0]] if s[0] in t else s[0]) + s[1:] for s in url[1:]])
        log(item.link)

    # reddit
    if urlparse(feedurl).netloc == 'www.reddit.com':
        match = lxml.html.fromstring(item.content).xpath('//a[text()="[link]"]/@href')
        if len(match):
            item.link = match[0]
            log(item.link)

    return item


def ItemFill(item, options, feedurl='/', fast=False):
    """ Returns True when it has done its best """

    if not item.link:
        log('no link')
        return True

    log(item.link)

    # download
    delay = -1

    if fast or options.fast:
        # force cache, don't fetch
        delay = -2

    elif options.force:
        # force refresh
        delay = 0

    else:
        delay = 24*60*60 # 24h

    try:
        req = crawler.adv_get(url=item.link, delay=delay, timeout=TIMEOUT)

    except (IOError, HTTPException) as e:
        log('http error')
        return False # let's just delete errors stuff when in cache mode

    if req['contenttype'] not in crawler.MIMETYPE['html'] and req['contenttype'] != 'text/plain':
        log('non-text page')
        return True

    out = readabilite.get_article(req['data'], url=req['url'], encoding_in=req['encoding'], encoding_out='unicode')

    if out is not None:
        item.content = out

    return True


def ItemBefore(item, options):
    # return None if item deleted

    if options.search:
        if options.search not in item.title:
            item.remove()
            return None

    return item


def ItemAfter(item, options):
    if options.clip and item.desc and item.content:
        item.content = item.desc + "<br/><br/><hr/><br/><br/>" + item.content
        del item.desc

    if options.nolink and item.content:
        content = lxml.html.fromstring(item.content)
        for link in content.xpath('//a'):
            log(link.text_content())
            link.drop_tag()
        item.content = lxml.etree.tostring(content, method='html')

    if options.noref:
        item.link = ''

    return item


def FeedFetch(url, options):
    # fetch feed
    delay = DELAY

    if options.force:
        delay = 0

    try:
        req = crawler.adv_get(url=url, follow=('rss' if not options.items else None), delay=delay, timeout=TIMEOUT * 2)

    except (IOError, HTTPException):
        raise MorssException('Error downloading feed')

    if options.items:
        # using custom rules
        rss = feeds.FeedHTML(req['data'], encoding=req['encoding'])

        rss.rules['title'] = options.title              if options.title        else '//head/title'
        rss.rules['desc'] = options.desc                if options.desc         else '//head/meta[@name="description"]/@content'

        rss.rules['items'] = options.items

        rss.rules['item_title'] = options.item_title    if options.item_title   else '.'
        rss.rules['item_link'] = options.item_link      if options.item_link    else './@href|.//a/@href|ancestor::a/@href'

        if options.item_content:
            rss.rules['item_content'] = options.item_content

        if options.item_time:
            rss.rules['item_time'] = options.item_time

        rss = rss.convert(feeds.FeedXML)

    else:
        try:
            rss = feeds.parse(req['data'], url=url, encoding=req['encoding'])
            rss = rss.convert(feeds.FeedXML)
                # contains all fields, otherwise much-needed data can be lost

        except TypeError:
            log('random page')
            log(req['contenttype'])
            raise MorssException('Link provided is not a valid feed')

    return req['url'], rss


def FeedGather(rss, url, options):
    size = len(rss.items)
    start_time = time.time()

    # custom settings
    lim_item = LIM_ITEM
    lim_time = LIM_TIME
    max_item = MAX_ITEM
    max_time = MAX_TIME

    if options.cache:
        max_time = 0

    if options.first:
        # :first to just take the first items in the feed (in sequence)
        sorted_items = rss.items

    else:
        # otherwise, take the _newest_, i.e. sort by time
        now = datetime.now(tz.tzutc())
        sorted_items = sorted(rss.items, key=lambda x:x.updated or x.time or now, reverse=True)

    for i, item in enumerate(sorted_items):
        if time.time() - start_time > lim_time >= 0 or i + 1 > lim_item >= 0:
            log('dropped')
            item.remove()
            continue

        item = ItemBefore(item, options)

        if item is None:
            continue

        item = ItemFix(item, options, url)

        if time.time() - start_time > max_time >= 0 or i + 1 > max_item >= 0:
            if not options.proxy:
                if ItemFill(item, options, url, True) is False:
                    item.remove()
                    continue

        else:
            if not options.proxy:
                ItemFill(item, options, url)

        item = ItemAfter(item, options)

    if options.ad:
        new = rss.items.append()
        new.title = "Are you hungry?"
        new.desc = "Eat some Galler chocolate :)"
        new.link = "http://www.galler.com/"
        new.time = "5 Oct 2013 22:42"

    log(len(rss.items))
    log(time.time() - start_time)

    return rss


def FeedFormat(rss, options, encoding='utf-8'):
    if options.callback:
        if re.match(r'^[a-zA-Z0-9\.]+$', options.callback) is not None:
            out = '%s(%s)' % (options.callback, rss.tojson(encoding='unicode'))
            return out if encoding == 'unicode' else out.encode(encoding)

        else:
            raise MorssException('Invalid callback var name')

    elif options.json:
        if options.indent:
            return rss.tojson(encoding=encoding, indent=4)

        else:
            return rss.tojson(encoding=encoding)

    elif options.csv:
        return rss.tocsv(encoding=encoding)

    elif options.html:
        if options.indent:
            return rss.tohtml(encoding=encoding, pretty_print=True)

        else:
            return rss.tohtml(encoding=encoding)

    else:
        if options.indent:
            return rss.torss(xml_declaration=(not encoding == 'unicode'), encoding=encoding, pretty_print=True)

        else:
            return rss.torss(xml_declaration=(not encoding == 'unicode'), encoding=encoding)


def process(url, cache=None, options=None):
    if not options:
        options = []

    options = Options(options)

    if cache:
        crawler.default_cache = crawler.SQLiteCache(cache)

    url, rss = FeedFetch(url, options)
    rss = FeedGather(rss, url, options)

    return FeedFormat(rss, options, 'unicode')


def cgi_parse_environ(environ):
    # get options

    if 'REQUEST_URI' in environ:
        url = environ['REQUEST_URI'][1:]
    else:
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
    options = Options(filterOptions(parseOptions(raw_options)))

    global DEBUG
    DEBUG = options.debug

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

    if options.html:
        headers['content-type'] = 'text/html'
    elif options.txt or options.silent:
        headers['content-type'] = 'text/plain'
    elif options.json:
        headers['content-type'] = 'application/json'
    elif options.callback:
        headers['content-type'] = 'application/javascript'
    elif options.csv:
        headers['content-type'] = 'text/csv'
        headers['content-disposition'] = 'attachment; filename="feed.csv"'
    else:
        headers['content-type'] = 'text/xml'

    headers['content-type'] += '; charset=utf-8'

    crawler.default_cache = crawler.SQLiteCache(os.path.join(os.getcwd(), 'morss-cache.db'))

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


cgi_standalone_app = cgi_encode(cgi_error_handler(cgi_dispatcher(cgi_file_handler(cgi_app))))


def cli_app():
    options = Options(filterOptions(parseOptions(sys.argv[1:-1])))
    url = sys.argv[-1]

    global DEBUG
    DEBUG = options.debug

    crawler.default_cache = crawler.SQLiteCache(os.path.expanduser('~/.cache/morss-cache.db'))

    url, rss = FeedFetch(url, options)
    rss = FeedGather(rss, url, options)
    out = FeedFormat(rss, options, 'unicode')

    if not options.silent:
        print(out)

    log('done')


def isInt(string):
    try:
        int(string)
        return True

    except ValueError:
        return False


def main():
    if 'REQUEST_URI' in os.environ:
        # mod_cgi

        app = cgi_app
        app = cgi_dispatcher(app)
        app = cgi_error_handler(app)
        app = cgi_encode(app)

        wsgiref.handlers.CGIHandler().run(app)

    elif len(sys.argv) <= 1 or isInt(sys.argv[1]):
        # start internal (basic) http server

        if len(sys.argv) > 1 and isInt(sys.argv[1]):
            argPort = int(sys.argv[1])
            if argPort > 0:
                port = argPort

            else:
                raise MorssException('Port must be positive integer')

        else:
            port = PORT

        app = cgi_app
        app = cgi_file_handler(app)
        app = cgi_dispatcher(app)
        app = cgi_error_handler(app)
        app = cgi_encode(app)

        print('Serving http://localhost:%s/' % port)
        httpd = wsgiref.simple_server.make_server('', port, app)
        httpd.serve_forever()

    else:
        # as a CLI app
        try:
            cli_app()

        except (KeyboardInterrupt, SystemExit):
            raise

        except Exception as e:
            print('ERROR: %s' % e.message)

if __name__ == '__main__':
    main()
