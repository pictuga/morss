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
import re
import time
from datetime import datetime
from fnmatch import fnmatch

import lxml.etree
import lxml.html
from dateutil import tz

from . import caching, crawler, feeds, readabilite

try:
    # python 2
    from httplib import HTTPException
    from urlparse import parse_qs, urljoin, urlparse
except ImportError:
    # python 3
    from http.client import HTTPException
    from urllib.parse import parse_qs, urljoin, urlparse


MAX_ITEM = int(os.getenv('MAX_ITEM', 5)) # cache-only beyond
MAX_TIME = int(os.getenv('MAX_TIME', 2)) # cache-only after (in sec)

LIM_ITEM = int(os.getenv('LIM_ITEM', 10)) # deletes what's beyond
LIM_TIME = int(os.getenv('LIM_TIME', 2.5)) # deletes what's after

DELAY = int(os.getenv('DELAY', 10 * 60)) # xml cache & ETag cache (in sec)
TIMEOUT = int(os.getenv('TIMEOUT', 4)) # http timeout (in sec)


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

    def __getattr__(self, key, default=None):
        if key in self.options:
            return self.options[key]

        else:
            return default

    def __setitem__(self, key, value):
        self.options[key] = value

    def __contains__(self, key):
        return key in self.options

    get = __getitem__ = __getattr__


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

    if fast or options.cache:
        # force cache, don't fetch
        policy = 'offline'

    elif options.force:
        # force refresh
        policy = 'refresh'

    else:
        policy = None

    try:
        req = crawler.adv_get(url=item.link, policy=policy, force_min=24*60*60, timeout=TIMEOUT)

    except (IOError, HTTPException) as e:
        log('http error')
        return False # let's just delete errors stuff when in cache mode

    if req['contenttype'] not in crawler.MIMETYPE['html'] and req['contenttype'] != 'text/plain':
        log('non-text page')
        return True

    if not req['data']:
        log('empty page')
        return True

    out = readabilite.get_article(req['data'], url=req['url'], encoding_in=req['encoding'], encoding_out='unicode', xpath=options.xpath)

    if out is not None:
        item.content = out

    if options.resolve:
        item.link = req['url']

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

    if options.cache:
        policy = 'offline'

    elif options.force:
        policy = 'refresh'

    else:
        policy = None

    try:
        req = crawler.adv_get(url=url, post=options.post, follow=('rss' if not options.items else None), policy=policy, force_min=5*60, force_max=60*60, timeout=TIMEOUT)

    except (IOError, HTTPException):
        raise MorssException('Error downloading feed')

    if options.items:
        # using custom rules
        ruleset = {}

        ruleset['items'] = options.items

        ruleset['title'] = options.get('title', '//head/title')
        ruleset['desc'] = options.get('desc', '//head/meta[@name="description"]/@content')

        ruleset['item_title'] = options.get('item_title', '.')
        ruleset['item_link'] = options.get('item_link', './@href|.//a/@href|ancestor::a/@href')

        if options.item_content:
            ruleset['item_content'] = options.item_content

        if options.item_time:
            ruleset['item_time'] = options.item_time

        rss = feeds.parse(req['data'], encoding=req['encoding'], ruleset=ruleset)
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
        # :newest take the newest items (instead of appearing order)
        now = datetime.now(tz.tzutc())
        sorted_items = sorted(rss.items, key=lambda x:x.updated or x.time or now, reverse=True)

    else:
        # default behavior, take the first items (in appearing order)
        sorted_items = list(rss.items)

    for i, item in enumerate(sorted_items):
        # hard cap
        if time.time() - start_time > lim_time >= 0 or i + 1 > lim_item >= 0:
            log('dropped')
            item.remove()
            continue

        item = ItemBefore(item, options)

        if item is None:
            continue

        item = ItemFix(item, options, url)

        # soft cap
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
        caching.default_cache = caching.SQLiteCache(cache)

    url, rss = FeedFetch(url, options)
    rss = FeedGather(rss, url, options)

    return FeedFormat(rss, options, 'unicode')
