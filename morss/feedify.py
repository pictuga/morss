#!/usr/bin/env python

import os.path

import re
import json

from fnmatch import fnmatch
import lxml.html

from . import feeds
from . import crawler

try:
    from ConfigParser import ConfigParser
    from urlparse import urljoin
    from httplib import HTTPException
except ImportError:
    from configparser import ConfigParser
    from urllib.parse import urljoin
    from http.client import HTTPException

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
    config.read(os.path.join(os.path.dirname(__file__), 'feedify.ini'))

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


def pre_worker(url):
    if url.startswith('http://itunes.apple.com/') or url.startswith('https://itunes.apple.com/'):
        match = re.search('/id([0-9]+)(\?.*)?$', url)
        if match:
            iid = match.groups()[0]
            redirect = 'https://itunes.apple.com/lookup?id=%s' % iid

            try:
                con = crawler.custom_handler(basic=True).open(redirect, timeout=4)
                data = con.read()

            except (IOError, HTTPException):
                raise

            return json.loads(data.decode('utf-8', 'replace'))['results'][0]['feedUrl']

    return None


class Builder(object):
    def __init__(self, link, data, rule=None):
        # data must be a unicode string

        self.link = link
        self.data = data
        self.rule = rule

        self.encoding = crawler.detect_encoding(self.data)

        if isinstance(self.data, bytes):
            self.data = self.data.decode(crawler.detect_encoding(self.data), 'replace')

        if self.rule is None:
            self.rule = get_rule(link)

        if self.rule['mode'] == 'xpath':
            self.doc = lxml.html.fromstring(self.data)

        elif self.rule['mode'] == 'json':
            self.doc = json.loads(self.data)

        self.feed = feeds.FeedXML()

    def raw(self, html, expr):
        " Returns selected items, thru a stupid query "

        if self.rule['mode'] == 'xpath':
            return html.xpath(to_class(expr))

        elif self.rule['mode'] == 'json':
            a = [html]
            b = []
            for x in expr.strip(".").split("."):
                match = re.search('^([^\[]+)(?:\[([0-9]+)\])?$', x).groups()
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
        " Turns the results of raw() into a nice array of strings (ie. sth useful) "

        if self.rule['mode'] == 'xpath':
            out = []
            for match in self.raw(html, expr):
                if isinstance(match, basestring):
                    out.append(match)
                elif isinstance(match, lxml.html.HtmlElement):
                    out.append(lxml.html.tostring(match))

        elif self.rule['mode'] == 'json':
            out = self.raw(html, expr)

        out = [x.decode(self.encoding) if isinstance(x, bytes) else x for x in out]
        return out

    def string(self, html, expr):
        " Makes a formatted string, using our custom template format, out of the getter and rule "

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
                        if url:
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
