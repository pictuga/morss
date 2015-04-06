#!/usr/bin/env python

import re
import json

from fnmatch import fnmatch
import lxml.html

from . import feeds
from . import crawler

try:
    from ConfigParser import ConfigParser
    from urlparse import urlparse, urljoin
    from urllib2 import urlopen
except ImportError:
    from configparser import ConfigParser
    from urllib.parse import urlparse, urljoin
    from urllib.request import urlopen

try:
    basestring
except NameError:
    basestring = str


def to_class(query):
    pattern = r'\[class=([^\]]+)\]'
    repl = r'[@class and contains(concat(" ", normalize-space(@class), " "), " \1 ")]'
    return re.sub(pattern, repl, query)


def get_rule(link):
    config = ConfigParser()
    config.read('feedify.ini')

    for section in config.sections():
        values = dict(config.items(section))
        values['path'] = values['path'].split('\n')[1:]
        for path in values['path']:
            if fnmatch(link, path):
                return values
    return False


def supported(link):
    return get_rule(link) is not False


def format_string(string, getter, error=False):
    out = ""
    char = string[0]

    follow = string[1:]

    if char == '"':
        match = follow.partition('"')
        out = match[0]
        if len(match) >= 2:
            next_match = match[2]
        else:
            next_match = None
    elif char == '{':
        match = follow.partition('}')
        try:
            test = format_string(match[0], getter, True)
        except (ValueError, KeyError):
            pass
        else:
            out = test

        next_match = match[2]
    elif char == ' ':
        next_match = follow
    elif re.search(r'^([^{}<>" ]+)(?:<"([^>]+)">)?(.*)$', string):
        match = re.search(r'^([^{}<>" ]+)(?:<"([^>]+)">)?(.*)$', string).groups()
        raw_value = getter(match[0])
        if not isinstance(raw_value, basestring):
            if match[1] is not None:
                out = match[1].join(raw_value)
            else:
                out = ''.join(raw_value)
        if not out and error:
            raise ValueError
        next_match = match[2]
    else:
        raise ValueError('bogus string')

    if next_match is not None and len(next_match):
        return out + format_string(next_match, getter, error)
    else:
        return out


def pre_worker(url, cache):
    if urlparse(url).netloc == 'itunes.apple.com':
        match = re.search('/id([0-9]+)(\?.*)?$', url)
        if match:
            iid = match.groups()[0]
            redirect = 'https://itunes.apple.com/lookup?id={id}'.format(id=iid)
            cache.set('redirect', redirect)


class Builder(object):
    def __init__(self, link, data=None, cache=False):
        self.link = link
        self.cache = cache

        if data is None:
            data = urlopen(link).read()
        self.data = data

        self.rule = get_rule(link)

        if self.rule['mode'] == 'xpath':
            if isinstance(self.data, bytes):
                self.data = self.data.decode(crawler.detect_encoding(self.data), 'replace')
            self.doc = lxml.html.fromstring(self.data)
        elif self.rule['mode'] == 'json':
            self.doc = json.loads(data)

        self.feed = feeds.FeedParserAtom()

    def raw(self, html, expr):
        " Returns selected items, thru a stupid query "

        if self.rule['mode'] == 'xpath':
            return html.xpath(to_class(expr))

        elif self.rule['mode'] == 'json':
            a = [html]
            b = []
            for x in expr.strip(".").split("."):
                match = re.search(r'^([^\[]+)(?:\[([0-9]+)\])?$', x).groups()
                for elem in a:
                    if isinstance(elem, dict):
                        kids = elem.get(match[0])
                        if kids is None:
                            pass
                        elif isinstance(kids, list):
                            b += kids
                        elif isinstance(kids, basestring):
                            b.append(kids.replace('\n', '<br/>'))
                        else:
                            b.append(kids)

                if match[1] is None:
                    a = b
                else:
                    if len(b) - 1 >= int(match[1]):
                        a = [b[int(match[1])]]
                    else:
                        a = []
                b = []
            return a

    def strings(self, html, expr):
        " Turns the results into a nice array of strings (ie. sth useful) "

        if self.rule['mode'] == 'xpath':
            out = []
            for match in self.raw(html, expr):
                if isinstance(match, basestring):
                    out.append(match)
                elif isinstance(match, lxml.html.HtmlElement):
                    out.append(lxml.html.tostring(match))
            return out

        elif self.rule['mode'] == 'json':
            return self.raw(html, expr)

    def string(self, html, expr):
        " Makes a formatted string out of the getter and rule "

        getter = lambda x: self.strings(html, x)
        return format_string(self.rule[expr], getter)

    def build(self):
        " Builds the actual rss feed "

        if 'title' in self.rule:
            self.feed.title = self.string(self.doc, 'title')

        if 'items' in self.rule:
            matches = self.raw(self.doc, self.rule['items'])
            if matches and len(matches):
                for item in matches:
                    feed_item = {}

                    if 'item_title' in self.rule:
                        feed_item['title'] = self.string(item, 'item_title')
                    if 'item_link' in self.rule:
                        url = self.string(item, 'item_link')
                        url = urljoin(self.link, url)
                        feed_item['link'] = url
                    if 'item_desc' in self.rule:
                        feed_item['desc'] = self.string(item, 'item_desc')
                    if 'item_content' in self.rule:
                        feed_item['content'] = self.string(item, 'item_content')
                    if 'item_time' in self.rule:
                        feed_item['updated'] = self.string(item, 'item_time')
                    if 'item_id' in self.rule:
                        feed_item['id'] = self.string(item, 'item_id')
                        feed_item['is_permalink'] = False

                    self.feed.items.append(feed_item)
