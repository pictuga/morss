import sys
import os
import os.path
import time

import threading

from fnmatch import fnmatch
import re
import json

import lxml.etree
import lxml.html

from . import feeds
from . import feedify
from . import crawler

import wsgiref.simple_server
import wsgiref.handlers

from html2text import HTML2Text

try:
    from Queue import Queue
    from httplib import HTTPException
    from urllib2 import build_opener
    from urllib2 import HTTPError
    from urllib import quote_plus
    from urlparse import urlparse, urljoin, parse_qs
except ImportError:
    from queue import Queue
    from http.client import HTTPException
    from urllib.request import build_opener
    from urllib.error import HTTPError
    from urllib.parse import quote_plus
    from urllib.parse import urlparse, urljoin, parse_qs

LIM_ITEM = 100  # deletes what's beyond
LIM_TIME = 7  # deletes what's after
MAX_ITEM = 50  # cache-only beyond
MAX_TIME = 7  # cache-only after (in sec)
DELAY = 10 * 60  # xml cache & ETag cache (in sec)
TIMEOUT = 4  # http timeout (in sec)
THREADS = 10  # number of threads (1 for single-threaded)

DEBUG = False
PORT = 8080

DEFAULT_UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:25.0) Gecko/20100101 Firefox/25.0'

MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}

PROTOCOL = ['http', 'https', 'ftp']


def filterOptions(options):
    return options

    # example of filtering code below

    #allowed = ['proxy', 'clip', 'keep', 'cache', 'force', 'silent', 'pro', 'debug']
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


try:
    from readability.readability import Document

    def readability(html, url=None):
        return Document(html, url=url).summary()
except ImportError:
    import breadability.readable

    def readability(html, url=None):
        return breadability.readable.Article(html, url=url).readable


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


default_handlers = [crawler.GZIPHandler(), crawler.UAHandler(DEFAULT_UA),
                    crawler.AutoRefererHandler(), crawler.HTTPEquivHandler(),
                    crawler.HTTPRefreshHandler(), crawler.EncodingFixHandler()]

def custom_handler(accept, delay=DELAY):
    handlers = default_handlers[:]
    handlers.append(crawler.ContentNegociationHandler(accept))
    handlers.append(crawler.SQliteCacheHandler(delay))

    return build_opener(*handlers)


def Fix(item, feedurl='/'):
    """ Improves feed items (absolute links, resolve feedburner links, etc) """

    # check unwanted uppercase title
    if len(item.title) > 20 and item.title.isupper():
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

    # check relative urls
    item.link = urljoin(feedurl, item.link)

    # Techmeme
    if fnmatch(item.link, 'http://www.techmeme.com/*'):
        #match = re.search('<A HREF="(.+?)"><IMG VSPACE="4"', item.desc)
        match_list = re.findall('<A HREF="(.+?)">', item.desc)
        for i in match_list:
            if not re.search('techmeme.com', i):
                match = i
                #break
        if match:
            #item.link = match.group(1)
            item.link = match
            log(item.link)

    # SeekingAlpha
    if fnmatch(item.link, 'http://seekingalpha.com/*'):
        match = re.sub('\?.*','',item.link)
        if match:
            item.link = match
            log(item.link)

    if fnmatch(item.link, 'http://www.reddit.com/r/scotch+whisky+worldwhisky*'):
        match = re.search('\\[link\\]\\<\\/a\\>\\ \\<a\\ href\\=\\"(.+?)">\\[', item.desc)
        if match:
            item.link = match.group(1)
            log(item.link)

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

    # facebook
    if fnmatch(item.link, 'https://www.facebook.com/l.php?u=*'):
        item.link = parse_qs(urlparse(item.link).query)['u'][0]
        log(item.link)

    # feedburner
    feeds.NSMAP['feedburner'] = 'http://rssnamespace.org/feedburner/ext/1.0'
    match = item.xval('feedburner:origLink')
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
        match = lxml.html.fromstring(item.desc).xpath('//a[text()="[link]"]/@href')
        if len(match):
            item.link = match[0]
            log(item.link)

    return item


def Fill(item, options, feedurl='/', fast=False):
    """ Returns True when it has done its best """

    if not item.link:
        log('no link')
        return item

    log(item.link)

    # content already provided?
    count_content = count_words(item.content)
    count_desc = count_words(item.desc)

    if not options.hungry and max(count_content, count_desc) > 500:
        if count_desc > count_content:
            item.content = item.desc
            del item.desc
            log('reversed sizes')
        log('long enough')
        return True

    if not options.hungry and count_content > 5 * count_desc > 0 and count_content > 50:
        log('content bigger enough')
        return True

    link = item.link

    # twitter
    if urlparse(feedurl).netloc == 'twitter.com':
        match = lxml.html.fromstring(item.content).xpath('//a/@data-expanded-url')
        if len(match):
            link = match[0]
            log(link)
        else:
            link = None

    # facebook
    if urlparse(feedurl).netloc == 'graph.facebook.com':
        match = lxml.html.fromstring(item.content).xpath('//a/@href')
        if len(match) and urlparse(match[0]).netloc != 'www.facebook.com':
            link = match[0]
            log(link)
        else:
            link = None

    if link is None:
        log('no used link')
        return True

    # download
    delay = -1

    if fast:
        # super-fast mode
        delay = -2

    try:
        con = custom_handler(('html', 'text/*'), delay).open(link, timeout=TIMEOUT)
        data = con.read()

    except (IOError, HTTPException) as e:
        log('http error')
        return False # let's just delete errors stuff when in cache mode

    contenttype = con.info().get('Content-Type', '').split(';')[0]
    if contenttype not in MIMETYPE['html'] and contenttype != 'text/plain':
        log('non-text page')
        return True

    out = readability(data, con.url)

    if options.hungry or count_words(out) > max(count_content, count_desc):
        item.push_content(out)

    else:
        log('link not bigger enough')
        return True

    return True


def Fetch(url, options):
    # basic url clean-up
    if url is None:
        raise MorssException('No url provided')

    if urlparse(url).scheme not in PROTOCOL:
        url = 'http://' + url
        log(url)

    url = url.replace(' ', '%20')

    if isinstance(url, bytes):
        url = url.decode()

    # do some useful facebook work
    pre = feedify.pre_worker(url)
    if pre:
        url = pre
        log('url redirect')
        log(url)

    # fetch feed
    delay = DELAY

    if options.theforce:
        delay = 0

    try:
        con = custom_handler(('xml', 'html'), delay).open(url, timeout=TIMEOUT * 2)
        xml = con.read()

    except (HTTPError) as e:
        raise MorssException('Error downloading feed (HTTP Error %s)' % e.code)

    except (IOError, HTTPException):
        raise MorssException('Error downloading feed')

    contenttype = con.info().get('Content-Type', '').split(';')[0]

    if url.startswith('https://itunes.apple.com/lookup?id='):
        link = json.loads(xml.decode('utf-8', 'replace'))['results'][0]['feedUrl']
        log('itunes redirect: %s' % link)
        return Fetch(link, options)

    elif xml.startswith(b'<?xml') or contenttype in MIMETYPE['xml']:
        rss = feeds.parse(xml)

    elif feedify.supported(url):
        feed = feedify.Builder(url, xml)
        feed.build()
        rss = feed.feed

    elif contenttype in MIMETYPE['html']:
        match = lxml.html.fromstring(xml).xpath(
            "//link[@rel='alternate'][@type='application/rss+xml' or @type='application/atom+xml']/@href")
        if len(match):
            link = urljoin(url, match[0])
            log('rss redirect: %s' % link)
            return Fetch(link, options)
        else:
            log('no-link html')
            raise MorssException('Link provided is an HTML page, which doesn\'t link to a feed')
    else:
        log('random page')
        log(contenttype)
        raise MorssException('Link provided is not a valid feed')

    return rss


def Gather(rss, url, options):
    size = len(rss.items)
    start_time = time.time()

    # custom settings
    lim_item = LIM_ITEM
    lim_time = LIM_TIME
    max_item = MAX_ITEM
    max_time = MAX_TIME
    threads = THREADS

    if options.cache:
        max_time = 0

    if options.mono:
        threads = 1

    # set
    def runner(queue):
        while True:
            value = queue.get()
            try:
                worker(*value)
            except Exception as e:
                log('Thread Error: %s' % e.message)
            queue.task_done()

    def worker(i, item):
        if time.time() - start_time > lim_time >= 0 or i + 1 > lim_item >= 0:
            log('dropped')
            item.remove()
            return

        item = Fix(item, url)

        if time.time() - start_time > max_time >= 0 or i + 1 > max_item >= 0:
            if not options.proxy:
                if Fill(item, options, url, True) is False:
                    item.remove()
                    return
        else:
            if not options.proxy:
                Fill(item, options, url)

    queue = Queue()

    for i in range(threads):
        t = threading.Thread(target=runner, args=(queue,))
        t.daemon = True
        t.start()

    for i, item in enumerate(list(rss.items)):
        if threads == 1:
            worker(*[i, item])
        else:
            queue.put([i, item])

    if threads != 1:
        queue.join()

    if options.ad:
        new = rss.items.append()
        new.title = "Are you hungry?"
        new.desc = "Eat some Galler chocolate :)"
        new.link = "http://www.galler.com/"
        new.time = "5 Oct 2013 22:42"

    log(len(rss.items))
    log(time.time() - start_time)

    return rss


def Before(rss, options):
    for i, item in enumerate(list(rss.items)):
        if options.smart and options.last:
            if item.time < feeds.parse_time(options.last) and i > 2:
                item.remove()
                continue

        if options.empty:
            item.remove()
            continue

        if options.search:
            if options.search not in item.title:
                item.remove()
                continue

    return rss


def After(rss, options):
    for i, item in enumerate(list(rss.items)):
        if options.strip:
            del item.desc
            del item.content

        if options.clip and item.desc and item.content:
            item.content = item.desc + "<br/><br/><center>* * *</center><br/><br/>" + item.content
            del item.desc

        if not options.keep and not options.proxy:
            del item.desc

        if options.nolink and item.content:
            content = lxml.html.fromstring(item.content)
            for link in content.xpath('//a'):
                log(link.text_content())
                link.drop_tag()
            item.content = lxml.etree.tostring(content)

        if options.noref:
            item.link = ''

        if options.md:
            conv = HTML2Text(baseurl=item.link)
            conv.unicode_snob = True

            if item.desc:
                item.desc = conv.handle(item.desc)
            if item.content:
                item.content = conv.handle(item.content)

    return rss


def Format(rss, options):
    if options.callback:
        if re.match(r'^[a-zA-Z0-9\.]+$', options.callback) is not None:
            return '%s(%s)' % (options.callback, rss.tojson())
        else:
            raise MorssException('Invalid callback var name')
    elif options.json:
        if options.indent:
            return rss.tojson(indent=4)
        else:
            return rss.tojson()
    elif options.csv:
        return rss.tocsv()
    elif options.reader:
        return rss.tohtml()
    else:
        if options.indent:
            return rss.tostring(xml_declaration=True, encoding='UTF-8', pretty_print=True)
        else:
            return rss.tostring(xml_declaration=True, encoding='UTF-8')


def process(url, cache=None, options=None):
    if not options:
        options = []

    options = Options(options)
    if cache: crawler.sqlite_default = cache
    rss = Fetch(url, options)
    rss = Before(rss, options)
    rss = Gather(rss, url, options)
    rss = After(rss, options)

    return Format(rss, options)


def cgi_app(environ, start_response):
    # get options
    if 'REQUEST_URI' in environ:
        url = environ['REQUEST_URI'][1:]
    else:
        url = environ['PATH_INFO'][1:]

    url = re.sub(r'^/?(morss.py|main.py|cgi/main.py)/', '', url)

    if url.startswith(':'):
        split = url.split('/', 1)
        options = split[0].split(':')[1:]
        if len(split) > 1:
            url = split[1]
        else:
            url = ''
    else:
        options = []

    # init
    options = Options(filterOptions(parseOptions(options)))
    headers = {}

    global DEBUG
    DEBUG = options.debug

    if 'HTTP_IF_NONE_MATCH' in environ:
        options['last'] = int(environ['HTTP_IF_NONE_MATCH'][1:-1])
        if not options.force and time.time() - options.last < DELAY:
            headers['status'] = '304 Not Modified'
            start_response(headers['status'], list(headers.items()))
            log(url)
            log('etag good')
            return []

    # headers
    headers['status'] = '200 OK'
    headers['etag'] = '"%s"' % int(time.time())

    if options.cors:
        headers['access-control-allow-origin'] = '*'

    if options.html or options.reader:
        headers['content-type'] = 'text/html'
    elif options.txt:
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

    crawler.sqlite_default = os.path.join(os.getcwd(), 'morss-cache.db')

    # get the work done
    rss = Fetch(url, options)

    if headers['content-type'] == 'text/xml':
        headers['content-type'] = rss.mimetype

    start_response(headers['status'], list(headers.items()))

    rss = Before(rss, options)
    rss = Gather(rss, url, options)
    rss = After(rss, options)
    out = Format(rss, options)

    if not options.silent:
        return out

    log('done')


def cgi_wrapper(environ, start_response):
    # simple http server for html and css
    files = {
        '': 'text/html',
        'index.html': 'text/html'}

    if 'REQUEST_URI' in environ:
        url = environ['REQUEST_URI'][1:]
    else:
        url = environ['PATH_INFO'][1:]

    if url in files:
        headers = {}

        if url == '':
            url = 'index.html'

        if '--root' in sys.argv[1:]:
            path = os.path.join(sys.argv[-1], url)

        else:
            path = url

        try:
            body = open(path, 'rb').read()

            headers['status'] = '200 OK'
            headers['content-type'] = files[url]
            start_response(headers['status'], list(headers.items()))
            return body

        except IOError:
            headers['status'] = '404 Not found'
            start_response(headers['status'], list(headers.items()))
            return 'Error %s' % headers['status']

    # actual morss use
    try:
        return cgi_app(environ, start_response) or []
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        headers = {'status': '500 Oops', 'content-type': 'text/plain'}
        start_response(headers['status'], list(headers.items()), sys.exc_info())
        log('ERROR <%s>: %s' % (url, e.message), force=True)
        return 'An error happened:\n%s' % e.message


def cli_app():
    options = Options(filterOptions(parseOptions(sys.argv[1:-1])))
    url = sys.argv[-1]

    global DEBUG
    DEBUG = options.debug

    crawler.sqlite_default = os.path.expanduser('~/.cache/morss-cache.db')

    rss = Fetch(url, options)
    rss = Before(rss, options)
    rss = Gather(rss, url, options)
    rss = After(rss, options)
    out = Format(rss, options)

    if not options.silent:
        print(out.decode('utf-8', 'replace') if isinstance(out, bytes) else out)

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
        wsgiref.handlers.CGIHandler().run(cgi_wrapper)

    elif len(sys.argv) <= 1 or isInt(sys.argv[1]) or '--root' in sys.argv[1:]:
        # start internal (basic) http server

        if isInt(sys.argv[1]):
            argPort = int(sys.argv[1])
            if argPort > 0:
                port = argPort
            else:
                raise MorssException('Port must be positive integer')

        else:
            port = PORT

        print('Serving http://localhost:%s/'%port)
        httpd = wsgiref.simple_server.make_server('', port, cgi_wrapper)
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
