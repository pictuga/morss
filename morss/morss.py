import os

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


try:
    # python 2
    from httplib import HTTPException
    from urlparse import urlparse, urljoin, parse_qs
except ImportError:
    # python 3
    from http.client import HTTPException
    from urllib.parse import urlparse, urljoin, parse_qs

MAX_ITEM = 5  # cache-only beyond
MAX_TIME = 2  # cache-only after (in sec)

LIM_ITEM = 10  # deletes what's beyond
LIM_TIME = 2.5  # deletes what's after

DELAY = 10 * 60  # xml cache & ETag cache (in sec)
TIMEOUT = 4  # http timeout (in sec)


class MorssException(Exception):
    pass


def log(txt):
    if 'DEBUG' in os.environ:
        if 'REQUEST_URI' in os.environ:
            # when running on Apache
            open('morss.log', 'a').write("%s\n" % repr(txt))

        else:
            # when using internal server or cli
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

    if options.newest:
        # :newest take the newest items
        now = datetime.now(tz.tzutc())
        sorted_items = sorted(rss.items, key=lambda x:x.updated or x.time or now, reverse=True)

    else:
        # default behavior, take the first items (in appearing order)
        sorted_items = list(rss.items)

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

    elif options.format == 'json':
        if options.indent:
            return rss.tojson(encoding=encoding, indent=4)

        else:
            return rss.tojson(encoding=encoding)

    elif options.format == 'csv':
        return rss.tocsv(encoding=encoding)

    elif options.format == 'html':
        if options.indent:
            return rss.tohtml(encoding=encoding, pretty_print=True)

        else:
            return rss.tohtml(encoding=encoding)

    else: # i.e. format == 'rss'
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
