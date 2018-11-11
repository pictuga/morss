#!/usr/bin/env python

import sys
import os.path

from datetime import datetime

import re
import json
import csv

from lxml import etree
from dateutil import tz
import dateutil.parser
from copy import deepcopy

from . import crawler

from wheezy.template.engine import Engine
from wheezy.template.loader import DictLoader
from wheezy.template.ext.core import CoreExtension

json.encoder.c_make_encoder = None

try:
    from collections import OrderedDict
except ImportError:
    # python < 2.7
    from ordereddict import OrderedDict

try:
    from StringIO import StringIO
    from urllib2 import urlopen
    from ConfigParser import ConfigParser
except ImportError:
    # python > 3
    from io import StringIO
    from urllib.request import urlopen
    from configparser import ConfigParser

try:
    basestring
except NameError:
    basestring = unicode = str


Element = etree.Element

NSMAP = {'atom': 'http://www.w3.org/2005/Atom',
         'atom03': 'http://purl.org/atom/ns#',
         'media': 'http://search.yahoo.com/mrss/',
         'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
         'slash': 'http://purl.org/rss/1.0/modules/slash/',
         'dc': 'http://purl.org/dc/elements/1.1/',
         'content': 'http://purl.org/rss/1.0/modules/content/',
         'rssfake': 'http://purl.org/rss/1.0/'}


def load(url):
    d = urlopen(url).read()
    return parse(d)


def tag_NS(tag, nsmap=NSMAP):
    match = re.search(r'^\{([^\}]+)\}(.*)$', tag)
    if match:
        match = match.groups()
        for (key, url) in nsmap.items():
            if url == match[0]:
                return "%s:%s" % (key, match[1].lower())
    else:
        match = re.search(r'^([^:]+):([^:]+)$', tag)
        if match:
            match = match.groups()
            if match[0] in nsmap:
                return "{%s}%s" % (nsmap[match[0]], match[1].lower())
    return tag


def parse_rules(filename=None):
    if not filename:
        filename = os.path.join(os.path.dirname(__file__), 'feedify.ini')

    config = ConfigParser()
    config.read(filename)

    rules = dict([(x, dict(config.items(x))) for x in config.sections()])

    for section in rules.keys():
        for arg in rules[section].keys():
            if '\n' in rules[section][arg]:
                rules[section][arg] = rules[section][arg].split('\n')[1:]

    return rules


class ParserBase(object):
    def __init__(self, data=None, rules=None):
        if rules is None:
            rules = parse_rules()['rss']

        if data is None:
            data = rules['base'][0]

        self.rules = rules
        self.root = self.parse(data)

        # do `if multi` and select the correct rule for each (and split \n)
        if isinstance(self.rules['items'], list):
            for (i, rule) in enumerate(self.rules['items']):
                if self.rule_search(rule) is not None:
                    key = i
                    break

            else:
                key = 0

            len_items = len(rules['items'])

            for arg in self.rules.keys():
                if (isinstance(self.rules[arg], list)
                        and len(self.rules[arg]) == len_items):
                    self.rules[arg] = self.rules[arg][key]

    def parse(self, raw):
        pass

    def remove(self):
        # delete oneslf
        pass

    def tostring(self):
        # output in its input format
        # to output in sth fancy (json, csv, html), change class type
        pass

    def tojson(self, indent=None):
        # TODO temporary
        return json.dumps(OrderedDict(self.iterdic()), indent=indent)

    def tocsv(self):
        # TODO temporary
        out = StringIO()
        c = csv.writer(out, dialect=csv.excel)

        for item in self.items:
            row = [getattr(item, x) for x in item.dic]

            if sys.version_info[0] < 3:
                row = [x.encode('utf-8') if isinstance(x, unicode) else x for x in row]

            c.writerow(row)

        out.seek(0)
        return out.read()

    def tohtml(self):
        # TODO temporary
        path = os.path.join(os.path.dirname(__file__), 'reader.html.template')
        loader = DictLoader({'reader': open(path).read()})
        engine = Engine(loader=loader, extensions=[CoreExtension()])
        template = engine.get_template('reader')
        return template.render({'feed': self}).encode('utf-8')

    def iterdic(self):
        for element in self.dic:
            value = getattr(self, element)

            if element == 'items':
                value = [OrderedDict(x.iterdic()) for x in value]
            elif isinstance(value, datetime):
                value = value.isoformat()

            yield element, value

    def rule_search(self, rule):
        # xpath, return the first one only
        try:
            return self.rule_search_all(rule)[0]

        except IndexError:
            return None

    def rule_search_all(self, rule):
        # xpath, return all (useful to find feed items)
        pass

    def rule_search_last(self, rule):
        # xpath, return the first one only
        try:
            return self.rule_search_all(rule)[-1]

        except IndexError:
            return None

    def rule_create(self, rule):
        # create node based on rule
        # (duplicate, copy existing (or template) or create from scratch, if possible)
        # --> might want to create node_duplicate helper fns
        pass

    def rule_remove(self, rule):
        # remove node from its parent
        pass

    def rule_set(self, rule, value):
        # value is always a str?
        pass

    def rule_str(self, rule):
        # GETs inside (pure) text from it
        pass

    def bool_prs(self, x):
        # parse
        pass

    def bool_fmt(self, x):
        # format
        pass

    def time_prs(self, x):
        # parse
        pass

    def time_fmt(self, x):
        # format
        pass

    def get_raw(self, rule_name):
        # get the raw output, for self.get_raw('items')
        pass

    def get_str(self, rule_name):
        # simple function to get nice text from the rule name
        # for use in @property, ie. self.get_str('title')
        pass

    def set_str(self, rule_name):
        pass

    def rmv(self, rule_name):
        # easy deleter
        pass


class ParserXML(ParserBase):
    def parse(self, raw):
        parser = etree.XMLParser(recover=True)
        return etree.fromstring(raw, parser)

    def remove(self):
        return self.root.getparent().remove(self.root)

    def tostring(self, **k):
        return etree.tostring(self.root, **k)

    def _rule_parse(self, rule):
        test = re.search(r'^(.*)/@([a-z]+)$', rule) # to match //div/a/@href
        return test.groups() if test else (rule, None)

    def _resolve_ns(self, rule):
        match = re.search(r'^([^:]+):([^:]+)$', rule) # to match fakerss:content
        if match:
            match = match.groups()
            if match[0] in NSMAP:
                return "{%s}%s" % (NSMAP[match[0]], match[1].lower())

        return rule

    @staticmethod
    def _inner_html(xml):
        return (xml.text or '') + ''.join([etree.tostring(child) for child in xml])

    @staticmethod
    def _clean_node(xml):
        [xml.remove(child) for child in xml]

    def rule_search_all(self, rule):
        try:
            return self.root.xpath(rule, namespaces=NSMAP)

        except etree.XPathEvalError:
            return []

    def rule_create(self, rule):
        # duplicate, copy from template or create from scratch
        rule, key = self._rule_parse(rule)

        # try recreating based on the rule (for really basic rules, ie. plain RSS)
        if re.search(r'^[a-zA-Z0-9/:]+$', rule):
            chain = rule.strip('/').split('/')
            current = self.root

            if rule[0] == '/':
                chain = chain[1:]

            for (i, node) in enumerate(chain):
                test = current.find(self._resolve_ns(node))

                if test and i < len(chain) - 1:
                    # yay, go on
                    current = test

                else:
                    # opps need to create
                    element = etree.Element(self._resolve_ns(node))
                    current.append(element)
                    current = element

            return current

        # try duplicating from existing (works well with fucked up structures)
        match = self.rule_search_last(rule)
        if match:
            element = deepcopy(match)
            match.getparen().append(element)
            return element

        # try duplicating from template
        # FIXME
        # >>> self.xml.getroottree().getpath(ff.find('a'))

        return None

    def rule_remove(self, rule):
        rule, key = self._rule_parse(rule)

        match = self.rule_search(rule)

        if key is not None:
            del x.attrib[key]

        else:
            match.getparent().remove(match)

    def rule_set(self, rule, value):
        rule, key = self._rule_parse(rule)

        match = self.rule_search(rule)

        if key is not None:
            match.attrib[key] = value

        else:
            if match is not None and len(match):
                # atom stuff
                self._clean_node(match)

                if match.attrib.get('type', '') == 'xhtml':
                    match.attrib['type'] = 'html'

            match.text = value

    def rule_str(self, rule):
        match = self.rule_search(rule)

        if isinstance(match, etree._Element):
            if len(match):
                # atom stuff
                return self._inner_html(match)

            else:
                return match.text or ""

        else:
            return match or ""

    def bool_prs(self, x):
        return (x or '').lower() != 'false'

    def bool_fmt(self, x):
        return 'true' if x else 'false'

    def time_prs(self, x):
        try:
            return parse_time(x)
        except ValueError:
            return None

    def time_fmt(self, x):
        try:
            time = parse_time(x)
            return time.strftime(self.rules['timeformat'])
        except ValueError:
            pass

    def get_raw(self, rule_name):
        return self.rule_search_all(self.rules[rule_name])

    def get_str(self, rule_name):
        return self.rule_str(self.rules[rule_name])

    def set_str(self, rule_name, value):
        try:
            return self.rule_set(self.rules[rule_name], value)

        except AttributeError:
            # does not exist, have to create it
            self.rule_create(self.rules[rule_name])
            return self.rule_set(self.rules[rule_name], value)

    def rmv(self, rule_name):
        self.rule_remove(self.rules[rule_name])


def parse_time(value):
    if isinstance(value, basestring):
        if re.match(r'^[0-9]+$', value):
            return datetime.fromtimestamp(int(value), tz.tzutc())
        else:
            return dateutil.parser.parse(value, tzinfos=tz.tzutc)
    elif isinstance(value, int):
        return datetime.fromtimestamp(value, tz.tzutc())
    elif isinstance(value, datetime):
        return value
    else:
        return False


class Uniq(object):
    _map = {}
    _id = None

    def __new__(cls, *args, **kwargs):
        # check if an item was already created for it
        # if so, reuse it
        # if not, create a new one

        tmp_id = cls._gen_id(*args, **kwargs)
        if tmp_id is not None and tmp_id in cls._map:
            return cls._map[tmp_id]

        else:
            obj = object.__new__(cls, *args, **kwargs)
            cls._map[obj._id] = obj
            return obj


class Feed(object):
    itemsClass = 'Item'
    dic = ('title', 'desc', 'items')

    def wrap_items(self, items):
        itemsClass = globals()[self.itemsClass]
        return [itemsClass(x, self.rules) for x in items]

    title = property(
        lambda f:   f.get_str('title'),
        lambda f,x: f.set_str('title', x),
        lambda f:   f.rmv('title') )
    description = desc = property(
        lambda f:   f.get_str('desc'),
        lambda f,x: f.set_str('desc', x),
        lambda f:   f.rmv('desc') )
    items = property(
        lambda f:   f )

    def append(self, new=None):
        self.rule_create(self.rules['items'])
        item = self.items[-1]

        if new is None:
            return item

        for attr in globals()[self.itemsClass].dic:
            if hasattr(new, attr):
                setattr(item, attr, getattr(new, attr))

            elif attr in new:
                setattr(item, attr, new[attr])

    def __getitem__(self, key):
        return self.wrap_items(self.get_raw('items'))[key]

    def __delitem__(self, key):
        self[key].rmv()

    def __len__(self):
        return len(self.get_raw('items'))


class FeedXML(Feed, ParserXML):
    itemsClass = 'ItemXML'

    def tostring(self, **k):
        return etree.tostring(self.root.getroottree(), **k)


class Item(Uniq):
    dic = ('title', 'link', 'desc', 'content', 'id', 'is_permalink', 'time', 'updated')

    def __init__(self, xml=None, rules=None):
        self._id = self._gen_id(xml)
        self.root = xml
        self.rules = rules

    @staticmethod
    def _gen_id(xml=None, *args, **kwargs):
        return id(xml)

    title = property(
        lambda f:   f.get_str('item_title'),
        lambda f,x: f.set_str('item_title', x),
        lambda f:   f.rmv('item_title') )
    link = property(
        lambda f:   f.get_str('item_link'),
        lambda f,x: f.set_str('item_link', x),
        lambda f:   f.rmv('item_link') )
    description = desc = property(
        lambda f:   f.get_str('item_desc'),
        lambda f,x: f.set_str('item_desc', x),
        lambda f:   f.rmv('item_desc') )
    content = property(
        lambda f:   f.get_str('item_content'),
        lambda f,x: f.set_str('item_content', x),
        lambda f:   f.rmv('item_content') )
    id = property(
        lambda f:   f.get_str('item_id'),
        lambda f,x: f.set_str('item_id', x),
        lambda f:   f.rmv('item_id') )
    is_permalink = property(
        lambda f:   f.get_str('item_is_permalink'),
        lambda f,x: f.set_str('item_is_permalink', x))#,
        #lambda f:   f.rmv('item_is_permalink') )
    time = property(
        lambda f:   f.time_fmt(f.get_str('item_time')),
        lambda f,x: f.set_str('title', f.time_prs(x)),
        lambda f:   f.rmv('item_time') )
    updated = property(
        lambda f:   f.time_fmt(f.get_str('item_updated')),
        lambda f,x: f.set_str('updated', f.time_prs(x)),
        lambda f:   f.rmv('item_updated') )


class ItemXML(Item, ParserXML):
    pass
