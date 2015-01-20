#!/usr/bin/env python
import sys
import os
import os.path
import time

import Queue
import threading

from fnmatch import fnmatch
import re
import json

import lxml.etree
import lxml.html

import feeds
import feedify
import crawler

import httplib
import urllib
import urllib2
import urlparse

import wsgiref.simple_server
import wsgiref.handlers

from readability import readability
from html2text import HTML2Text

LIM_ITEM = 100  # deletes what's beyond
LIM_TIME = 7  # deletes what's after
MAX_ITEM = 50  # cache-only beyond
MAX_TIME = 7  # cache-only after (in sec)
DELAY = 10 * 60  # xml cache & ETag cache (in sec)
TIMEOUT = 2  # http timeout (in sec)
THREADS = 10  # number of threads (1 for single-threaded)

DEBUG = False

CA_CERT = 'cacert.pem' # ca cert file
DEFAULT_UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:25.0) Gecko/20100101 Firefox/25.0'

MIMETYPE = {
    'xml': ['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
    'html': ['text/html', 'application/xhtml+xml', 'application/xml']}

PROTOCOL = ['http', 'https', 'ftp']

if 'SCRIPT_NAME' in os.environ:
    httplib.HTTPConnection.debuglevel = 1

    import cgitb

    cgitb.enable()


class MorssException(Exception):
    pass


def log(txt, force=False):
    if DEBUG or force:
        if 'REQUEST_URI' in os.environ:
            open('morss.log', 'a').write("%s\n" % repr(txt))
        else:
            print repr(txt)


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


class Cache:
    """ Light, error-prone caching system. """

    def __init__(self, folder=None, key='cache', lifespan=10 * 24 * 3600):
        self._key = key
        self._dir = folder
        self._lifespan = lifespan

        self._cache = {}

        if self._dir is None:
            self._hash = "NO CACHE"
            return

        maxsize = os.statvfs('./').f_namemax - len(self._dir) - 1 - 4  # ".tmp"
        self._hash = urllib.quote_plus(self._key)[:maxsize]

        self._file = self._dir + '/' + self._hash
        self._file_tmp = self._file + '.tmp'

        try:
            data = open(self._file).read()
            if data:
                self._cache = json.loads(data)
        except IOError:
            pass
        except ValueError:
            log('JSON cache parse fail')

    def __del__(self):
        self.save()

    def __contains__(self, key):
        return key in self._cache

    def get(self, key):
        if key in self._cache:
            self._cache[key]['last'] = time.time()
            return self._cache[key]['value']
        else:
            return None

    def set(self, key, content):
        self._cache[key] = {'last': time.time(), 'value': content}

    __getitem__ = get
    __setitem__ = set

    def save(self):
        if len(self._cache) == 0 or self._dir is None:
            return

        if not os.path.exists(self._dir):
            os.makedirs(self._dir)

        for i in self._cache.keys():
            if time.time() - self._cache[i]['last'] > self._lifespan > -1:
                del self._cache[i]

        out = json.dumps(self._cache, indent=4)

        try:
            open(self._file_tmp, 'w+').write(out)
            os.rename(self._file_tmp, self._file)
        except IOError:
            log('failed to write cache to tmp file')
        except OSError:
            log('failed to move cache to file')

    def last(self, key):
        if key not in self._cache:
            return -1

        return self._cache[key]['last']

    def age(self, key):
        if key not in self._cache:
            return -1

        return time.time() - self.last(key)

    def new(self, *arg, **karg):
        """ Returns a Cache object in the same directory """
        if arg[0] != self._key:
            return Cache(self._dir, *arg, **karg)
        else:
            return self


default_handlers = [crawler.VerifiedHTTPSHandler(ca_certs=CA_CERT),
                    crawler.GZIPHandler(), crawler.UAHandler(DEFAULT_UA),
                    crawler.AutoRefererHandler(), crawler.MetaRedirectHandler(),
                    crawler.EncodingFixHandler()]

def accept_handler(*kargs):
    handlers = default_handlers[:]
    handlers.append(crawler.ContentNegociationHandler(*kargs))
    return handlers

def etag_handler(accept, strict, cache, etag, lastmodified):
    handlers = default_handlers[:]
    handlers.append(crawler.ContentNegociationHandler(accept, strict))
    handlers.append(crawler.EtagHandler(cache, etag, lastmodified))
    return handlers


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
    item.link = urlparse.urljoin(feedurl, item.link)

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
        item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['u'][0]
        log(item.link)

    # google
    if fnmatch(item.link, 'http://www.google.*/url?q=*'):
        item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['q'][0]
        log(item.link)

    # google news
    if fnmatch(item.link, 'http://news.google.com/news/url*url=*'):
        item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['url'][0]
        log(item.link)

    # facebook
    if fnmatch(item.link, 'https://www.facebook.com/l.php?u=*'):
        item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['u'][0]
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
        t = {'A': '0', 'B': '.', 'C': '/', 'D': '?', 'E': '-', 'H': ',', 'I': '_', 'L': 'http://', 'S': 'www.',
             'N': '.com', 'O': '.co.uk'}
        item.link = ''.join([(t[s[0]] if s[0] in t else '=') + s[1:] for s in url[1:]])
        log(item.link)

    # reddit
    if urlparse.urlparse(feedurl).netloc == 'www.reddit.com':
        match = lxml.html.fromstring(item.desc).xpath('//a[text()="[link]"]/@href')
        if len(match):
            item.link = match[0]
            log(item.link)

    return item


def Fill(item, cache, options, feedurl='/', fast=False):
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
    if urlparse.urlparse(feedurl).netloc == 'twitter.com':
        match = lxml.html.fromstring(item.content).xpath('//a/@data-expanded-url')
        if len(match):
            link = match[0]
            log(link)
        else:
            link = None

    # facebook
    if urlparse.urlparse(feedurl).netloc == 'graph.facebook.com':
        match = lxml.html.fromstring(item.content).xpath('//a/@href')
        if len(match) and urlparse.urlparse(match[0]).netloc != 'www.facebook.com':
            link = match[0]
            log(link)
        else:
            link = None

    if link is None:
        log('no used link')
        return True

    # check cache and previous errors
    if link in cache:
        content = cache.get(link)
        match = re.search(r'^error-([a-z]{2,10})$', content)
        if match:
            if cache.age(link) > DELAY:
                log('cached error: %s' % match.groups()[0])
                return True
            else:
                log('old error')
        else:
            log('cached')
            item.push_content(cache.get(link))
            return True

    # super-fast mode
    if fast:
        log('skipped')
        return False

    # download
    try:
        url = link.encode('utf-8')
        con = urllib2.build_opener(*accept_handler(('html', 'text/*'), True)).open(url, timeout=TIMEOUT)
        data = con.read()
    except (IOError, httplib.HTTPException) as e:
        log('http error:  %s' % e.message)
        cache.set(link, 'error-http')
        return True

    if con.info().type not in MIMETYPE['html'] and con.info().type != 'text/plain':
        log('non-text page')
        cache.set(link, 'error-type')
        return True

    out = readability.Document(data, url=con.url).summary(True)

    if count_words(out) > max(count_content, count_desc) > 0:
        item.push_content(out)
        cache.set(link, out)
    else:
        log('not bigger enough')
        cache.set(link, 'error-length')
        return True

    return True


def Init(url, cache_path, options):
    # url clean up
    log(url)

    if url is None:
        raise MorssException('No url provided')

    if urlparse.urlparse(url).scheme not in PROTOCOL:
        url = 'http://' + url
        log(url)

    url = url.replace(' ', '%20')

    # cache
    cache = Cache(cache_path, url)
    log(cache._hash)

    return (url, cache)


def Fetch(url, cache, options):
    # do some useful facebook work
    feedify.pre_worker(url, cache)

    if 'redirect' in cache:
        url = cache.get('redirect')
        log('url redirect')
        log(url)

    # fetch feed
    if not options.theforce and 'xml' in cache and cache.age('xml') < DELAY and 'style' in cache:
        log('xml cached')
        xml = cache.get('xml')
        style = cache.get('style')
    else:
        try:
            opener = etag_handler(('xml', 'html'), False, cache.get(url), cache.get('etag'), cache.get('lastmodified'))
            con = urllib2.build_opener(*opener).open(url, timeout=TIMEOUT * 2)
            xml = con.read()
        except (urllib2.HTTPError) as e:
            raise MorssException('Error downloading feed (HTTP Error %s)' % e.code)
        except (crawler.InvalidCertificateException) as e:
            raise MorssException('Error downloading feed (Invalid SSL Certificate)')
        except (IOError, httplib.HTTPException):
            raise MorssException('Error downloading feed')

        cache.set('xml', xml)
        cache.set('etag', con.headers.getheader('etag'))
        cache.set('lastmodified', con.headers.getheader('last-modified'))

        if url.startswith('https://itunes.apple.com/lookup?id='):
            style = 'itunes'
        elif xml.startswith('<?xml') or con.info().type in MIMETYPE['xml']:
            style = 'normal'
        elif feedify.supported(url):
            style = 'feedify'
        elif con.info().type in MIMETYPE['html']:
            style = 'html'
        else:
            style = 'none'
            log(con.info().type)

        cache.set('style', style)

    # decide what to do
    log(style)

    if style == 'itunes':
        link = json.loads(xml)['results'][0]['feedUrl']
        log('itunes redirect: %s' % link)
        return Fetch(link, cache.new(link), options)
    elif style == 'normal':
        rss = feeds.parse(xml)
    elif style == 'feedify':
        feed = feedify.Builder(url, xml, cache)
        feed.build()
        rss = feed.feed
    elif style == 'html':
        match = lxml.html.fromstring(xml).xpath(
            "//link[@rel='alternate'][@type='application/rss+xml' or @type='application/atom+xml']/@href")
        if len(match):
            link = urlparse.urljoin(url, match[0])
            log('rss redirect: %s' % link)
            return Fetch(link, cache.new(link), options)
        else:
            log('no-link html')
            raise MorssException('Link provided is an HTML page, which doesn\'t link to a feed')
    else:
        log('random page')
        raise MorssException('Link provided is not a valid feed')

    cache.save()
    return rss


def Gather(rss, url, cache, options):
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
                if Fill(item, cache, options, url, True) is False:
                    item.remove()
                    return
        else:
            if not options.proxy:
                Fill(item, cache, options, url)

    queue = Queue.Queue()

    for i in xrange(threads):
        t = threading.Thread(target=runner, args=(queue,))
        t.daemon = True
        t.start()

    for i, item in enumerate(list(rss.items)):
        queue.put([i, item])

    queue.join()
    cache.save()

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

        if item.desc and item.content:
            if options.clip:
                item.content = item.desc + "<br/><br/><center>* * *</center><br/><br/>" + item.content
                del item.desc
            if not options.keep:
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
        return rss.tostring(xml_declaration=True, encoding='UTF-8')


def process(url, cache=None, options=None):
    if not options:
        options = []

    options = Options(options)
    url, cache = Init(url, cache, options)
    rss = Fetch(url, cache, options)
    rss = Before(rss, options)
    rss = Gather(rss, url, cache, options)
    rss = After(rss, options)

    return Format(rss, options)


def cgi_app(environ, start_response):
    # get options
    if 'REQUEST_URI' in environ:
        url = environ['REQUEST_URI'][1:]
    else:
        url = environ['PATH_INFO'][1:]

    url = re.sub(r'^/?morss.py/', '', url)

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
    options = Options(parseOptions(options))
    headers = {}

    global DEBUG
    DEBUG = options.debug

    if 'HTTP_IF_NONE_MATCH' in environ:
        options['last'] = int(environ['HTTP_IF_NONE_MATCH'][1:-1])
        if not options.force and time.time() - options.last < DELAY:
            headers['status'] = '304 Not Modified'
            start_response(headers['status'], headers.items())
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

    url, cache = Init(url, os.getcwd() + '/cache', options)

    # get the work done
    rss = Fetch(url, cache, options)

    if headers['content-type'] == 'text/xml':
        headers['content-type'] = rss.mimetype

    start_response(headers['status'], headers.items())

    rss = Before(rss, options)
    rss = Gather(rss, url, cache, options)
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

        if os.path.isfile(url):
            headers['status'] = '200 OK'
            headers['content-type'] = files[url]
            start_response(headers['status'], headers.items())
            return open(url, 'rb').read()
        else:
            headers['status'] = '404 Not found'
            start_response(headers['status'], headers.items())
            return ''

    # actual morss use
    try:
        return cgi_app(environ, start_response) or []
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        headers = {'status': '500 Oops', 'content-type': 'text/plain'}
        start_response(headers['status'], headers.items(), sys.exc_info())
        log('ERROR <%s>: %s' % (url, e.message), force=True)
        return 'An error happened:\n%s' % e.message


def cli_app():
    options = Options(parseOptions(sys.argv[1:-1]))
    url = sys.argv[-1]

    global DEBUG
    DEBUG = options.debug

    url, cache = Init(url, os.path.expanduser('~/.cache/morss'), options)
    rss = Fetch(url, cache, options)
    rss = Before(rss, options)
    rss = Gather(rss, url, cache, options)
    rss = After(rss, options)
    out = Format(rss, options)

    if not options.silent:
        print out

    log('done')


def main():
    if 'REQUEST_URI' in os.environ:
        wsgiref.handlers.CGIHandler().run(cgi_wrapper)

    elif len(sys.argv) <= 1:
        httpd = wsgiref.simple_server.make_server('', 8080, cgi_wrapper)
        httpd.serve_forever()

    else:
        try:
            cli_app()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            print 'ERROR: %s' % e.message

if __name__ == '__main__':
    main()
