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
except ImportError:
    # python > 3
    from io import StringIO
    from urllib.request import urlopen

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


def inner_html(xml):
    return (xml.text or '') + ''.join([etree.tostring(child) for child in xml])


def clean_node(xml):
    [xml.remove(child) for child in xml]


class FeedException(Exception):
    pass


def parse(data):
    # parse
    parser = etree.XMLParser(recover=True)
    doc = etree.fromstring(data, parser)

    # rss
    match = doc.xpath("//atom03:feed|//atom:feed|//channel|//rdf:rdf|//rdf:RDF", namespaces=NSMAP)
    if len(match):
        m_table = {'rdf:rdf': FeedParserRSS, 'channel': FeedParserRSS,
                   'atom03:feed': FeedParserAtom, 'atom:feed': FeedParserAtom}
        match = match[0]
        tag = tag_NS(match.tag)
        if tag in m_table:
            return m_table[tag](doc, tag)

    raise FeedException('unknown feed type')


class FeedBase(object):
    """
    Base for xml-related classes, which provides simple wrappers around xpath
    selection and item creation
    """

    def iterdic(self):
        for element in self.dic:
            value = getattr(self, element)

            if element == 'items':
                value = [OrderedDict(x.iterdic()) for x in value]
            elif isinstance(value, datetime):
                value = value.isoformat()

            yield element, value

    def xpath(self, path):
        """ Test xpath rule on xml tree """
        return self.root.xpath(path, namespaces=NSMAP)

    def xget(self, path):
        """ Returns the 1st xpath match """
        match = self.xpath(path)
        if len(match):
            return match[0]
        else:
            return None

    def xval(self, path):
        """ Returns the .text of the 1st match """
        match = self.xget(path)
        if match is not None:
            return match.text or ""
        else:
            return ""

    def xget_create(self, table):
        """ Returns an element, and creates it when not present """
        value = table[self.tag]
        if not isinstance(value, tuple):
            value = (value, value)
        new, xpath = value
        match = self.xget(xpath)
        if match is not None:
            return match
        else:
            element = etree.Element(tag_NS(new))
            self.root.append(element)
            return element

    def xdel(self, path):
        match = self.xget(path)
        if match is not None:
            return match.getparent().remove(match)

    def tostring(self, **k):
        """ Returns string using lxml. Arguments passed to tostring """
        return etree.tostring(self.xml, **k)


class FeedDescriptor(object):
    """
    Descriptor which gives off elements based on "self.getName" and
    "self.setName" as getter/setters. Looks far better, and avoids duplicates
    """

    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % self.name)
        return getter()

    def __set__(self, instance, value):
        setter = getattr(instance, 'set_%s' % self.name)
        return setter(value)

    def __delete__(self, instance):
        deleter = getattr(instance, 'del_%s' % self.name)
        return deleter()


class FeedTime(FeedDescriptor):
    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % self.name)
        raw = getter()
        try:
            time = parse_time(raw)
            return time
        except ValueError:
            return None

    def __set__(self, instance, value):
        try:
            time = parse_time(value)
            raw = time.strftime(instance.timeFormat)
            setter = getattr(instance, 'set_%s' % self.name)
            return setter(raw)
        except ValueError:
            pass


class FeedBool(FeedDescriptor):
    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % self.name)
        raw = getter()
        return (raw or '').lower() != 'false'

    def __set__(self, instance, value):
        raw = 'true' if value else 'false'
        setter = getattr(instance, 'set_%s' % self.name)
        return setter(raw)


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
            obj.__init__(*args, **kwargs)
            cls._map[obj._id] = obj
            return obj


class FeedParser(FeedBase):
    itemsClass = 'FeedItem'
    mimetype = 'application/xml'
    base = b'<?xml?>'
    dic = ('title', 'desc', 'items')

    def __init__(self, xml=None, tag='atom:feed'):
        if xml is None:
            xml = etree.fromstring(self.base[tag])
        self.xml = xml
        self.root = self.xml.xpath("//atom03:feed|//atom:feed|//channel|//rssfake:channel", namespaces=NSMAP)[0]
        self.tag = tag

        self.itemsClass = globals()[self.itemsClass]

    def get_title(self):
        return ""

    def set_title(self, value):
        pass

    def del_title(self):
        self.title = ""

    def get_desc(self):
        pass

    def set_desc(self, value):
        pass

    def del_desc(self):
        self.desc = ""

    def get_items(self):
        return []

    def wrap_items(self, items):
        return [self.itemsClass(x, self.tag) for x in items]

    title = property(
        lambda f:   f.get_title(),
        lambda f,x: f.set_title(x),
        lambda f:   f.del_title() )
    description = desc = property(
        lambda f:   f.get_desc(),
        lambda f,x: f.set_desc(x),
        lambda f:   f.del_desc() )
    items = property(
        lambda f:   f )

    def append(self, cousin=None):
        new = self.itemsClass(tag=self.tag)
        self.root.append(new.xml)

        if cousin is None:
            return new

        for attr in self.itemsClass.dic:
            if hasattr(cousin, attr):
                setattr(new, attr, getattr(cousin, attr))

            elif attr in cousin:
                setattr(new, attr, cousin[attr])

        return new

    def __getitem__(self, key):
        return self.wrap_items(self.get_items())[key]

    def __delitem__(self, key):
        self[key].remove()

    def __len__(self):
        return len(self.get_items())

    def tostring(self, **k):
        return etree.tostring(self.xml.getroottree(), **k)

    def tojson(self, indent=None):
        return json.dumps(OrderedDict(self.iterdic()), indent=indent)

    def tocsv(self):
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
        path = os.path.join(os.path.dirname(__file__), 'reader.html.template')
        loader = DictLoader({'reader': open(path).read()})
        engine = Engine(loader=loader, extensions=[CoreExtension()])
        template = engine.get_template('reader')
        return template.render({'feed': self}).encode('utf-8')


class FeedParserRSS(FeedParser):
    """
    RSS Parser
    """
    itemsClass = 'FeedItemRSS'
    mimetype = 'application/rss+xml'
    base = {
        'rdf:rdf': b'<?xml version="1.0" encoding="utf-8"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><channel rdf:about="http://example.org/rss.rdf"></channel></rdf:RDF>',
        'channel': b'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel></channel></rss>'}

    def get_title(self):
        return self.xval('rssfake:title|title')

    def set_title(self, value):
        if not value:
            return self.xdel('rssfake:title|title')

        table = {'rdf:rdf': 'rssfake:title',
                 'channel': 'title'}
        element = self.xget_create(table)
        element.text = value

    def get_desc(self):
        return self.xval('rssfake:description|description')

    def set_desc(self, value):
        if not value:
            return self.xdel('rssfake:description|description')

        table = {'rdf:rdf': 'rssfake:description',
                 'channel': 'description'}
        element = self.xget_create(table)
        element.text = value

    def get_items(self):
        return self.xpath('rssfake:item|item')


class FeedParserAtom(FeedParser):
    """
    Atom Parser
    """
    itemsClass = 'FeedItemAtom'
    mimetype = 'application/atom+xml'
    base = {'atom:feed': b'<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
            'atom03:feed': b'<?xml version="1.0" encoding="utf-8"?><feed version="0.3" xmlns="http://purl.org/atom/ns#"></feed>'}

    def get_title(self):
        return self.xval('atom:title|atom03:title')

    def set_title(self, value):
        if not value:
            return self.xval('atom:title|atom03:title')

        table = {'atom:feed': 'atom:title',
                 'atom03:feed': 'atom03:title'}
        element = self.xget_create(table)
        element.text = value

    def get_desc(self):
        return self.xval('atom:subtitle|atom03:subtitle')

    def set_desc(self, value):
        if not value:
            return self.xdel('atom:subtitle|atom03:subtitle')

        table = {'atom:feed': 'atom:subtitle',
                 'atom03:feed': 'atom03:subtitle'}
        element = self.xget_create(table)
        element.text = value

    def get_items(self):
        return self.xpath('atom:entry|atom03:entry')


class FeedItem(FeedBase, Uniq):
    timeFormat = ''
    dic = ('title', 'link', 'desc', 'content', 'id', 'is_permalink', 'time', 'updated')

    def __init__(self, xml=None, tag='atom:feed'):
        if xml is None:
            xml = Element(tag_NS(self.base[tag]))

        self._id = FeedItem._gen_id(xml)

        self.root = self.xml = xml
        self.tag = tag

    @classmethod
    def _gen_id(cls, xml=None, *args, **kwargs):
        if xml is not None:
            return id(xml)

        else:
            return None

    def get_title(self):
        return ""

    def set_title(self, value):
        pass

    def del_title(self):
        self.title = ""

    def get_link(self):
        return ""

    def set_link(self, value):
        pass

    def del_link(self):
        self.link = ""

    def get_is_permalink(self):
        return ""

    def set_is_permalink(self, value):
        pass

    def get_desc(self):
        return ""

    def set_desc(self, value):
        pass

    def del_desc(self):
        self.desc = ""

    def get_content(self):
        return ""

    def set_content(self, value):
        pass

    def del_content(self):
        self.content = ""

    def get_id(self):
        return ""

    def set_id(self, value):
        pass

    def del_id(self):
        self.id = ""

    def get_time(self):
        return None

    def set_time(self, value):
        pass

    def delTime(self):
        self.time = None

    def get_updated(self):
        return None

    def set_updated(self, value):
        pass

    def del_updated(self):
        self.updated = None

    title = property(
        lambda f:   f.get_title(),
        lambda f,x: f.set_title(x),
        lambda f:   f.del_title() )
    link = property(
        lambda f:   f.get_link(),
        lambda f,x: f.set_link(x),
        lambda f:   f.del_link() )
    description = desc = property(
        lambda f:   f.get_desc(),
        lambda f,x: f.set_desc(x),
        lambda f:   f.del_desc() )
    content = property(
        lambda f:   f.get_content(),
        lambda f,x: f.set_content(x),
        lambda f:   f.del_content() )
    id = property(
        lambda f:   f.get_id(),
        lambda f,x: f.set_id(x),
        lambda f:   f.del_id() )
    is_permalink = FeedBool('is_permalink')
    time = FeedTime('time')
    updated = FeedTime('updated')

    def push_content(self, value):
        if not self.desc and self.content:
            self.desc = self.content

        self.content = value

    def remove(self):
        self.xml.getparent().remove(self.xml)


class FeedItemRSS(FeedItem):
    timeFormat = '%a, %d %b %Y %H:%M:%S %Z'
    base = {'rdf:rdf': 'rssfake:item',
            'channel': 'item'}

    def get_title(self):
        return self.xval('rssfake:title|title')

    def set_title(self, value):
        if not value:
            return self.xdel('rssfake:title|title')

        table = {'rdf:rdf': 'rssfake:title',
                 'channel': 'title'}
        element = self.xget_create(table)
        element.text = value

    def get_link(self):
        return self.xval('rssfake:link|link')

    def set_link(self, value):
        if self.is_permalink and self.id == self.link != value:
            self.is_permalink = False

        table = {'rdf:rdf': 'rssfake:link',
                 'channel': 'link'}
        element = self.xget_create(table)
        element.text = value

    def get_desc(self):
        return self.xval('rssfake:description|description')

    def set_desc(self, value):
        if not value:
            return self.xdel('rssfake:description|description')

        table = {'rdf:rdf': 'rssfake:description',
                 'channel': 'description'}
        element = self.xget_create(table)
        element.text = value

    def get_content(self):
        return self.xval('content:encoded')

    def set_content(self, value):
        if not value:
            return self.xdel('content:encoded')

        table = {'rdf:rdf': 'content:encoded',
                 'channel': 'content:encoded'}
        element = self.xget_create(table)
        element.text = value

    def get_id(self):
        return self.xval('rssfake:guid|guid')

    def set_id(self, value):
        if not value:
            return self.xdel('rssfake:guid|guid')

        table = {'rdf:rdf': 'rssfake:guid',
                 'channel': 'guid'}
        element = self.xget_create(table)
        element.text = value

    def get_is_permalink(self):
        return self.xget('rssfake:guid/@isPermaLink|guid/@isPermaLink')

    def set_is_permalink(self, value):
        table = {'rdf:rdf': 'rssfake:guid',
                 'channel': 'guid'}
        element = self.xget_create(table)
        element.attrib['isPermaLink'] = value

    def get_time(self):
        return self.xval('rssfake:pubDate|pubDate')

    def set_time(self, value):
        if not value:
            return self.xdel('rssfake:pubDate|pubDate')

        table = {'rdf:rdf': 'rssfake:pubDate',
                 'channel': 'pubDate'}
        element = self.xget_create(table)
        element.text = value


class FeedItemAtom(FeedItem):
    timeFormat = '%Y-%m-%dT%H:%M:%SZ'
    base = {'atom:feed': 'atom:entry',
            'atom03:feed': 'atom03:entry'}

    def get_title(self):
        return self.xval('atom:title|atom03:title')

    def set_title(self, value):
        if not value:
            return self.xdel('atom:title|atom03:title')

        table = {'atom:feed': 'atom:title',
                 'atom03:feed': 'atom03:title'}
        element = self.xget_create(table)
        element.text = value

    def get_link(self):
        return self.xget('(atom:link|atom03:link)[@rel="alternate" or not(@rel)]/@href')

    def set_link(self, value):
        table = {'atom:feed': ('atom:link', 'atom:link[@rel="alternate" or not(@rel)]'),
                 'atom03:feed': ('atom03:link', 'atom03:link[@rel="alternate" or not(@rel)]')}
        element = self.xget_create(table)
        element.attrib['href'] = value

    def get_desc(self):
        # default "type" is "text"
        element = self.xget('atom:summary|atom03:summary')
        if element is not None:
            return inner_html(element)
        else:
            return ""

    def set_desc(self, value):
        if not value:
            return self.xdel('atom:summary|atom03:summary')

        table = {'atom:feed': 'atom:summary',
                 'atom03:feed': 'atom03:summary'}
        element = self.xget_create(table)
        if element.attrib.get('type', '') == 'xhtml':
            clean_node(element)
        element.attrib['type'] = 'html'
        element.text = value

    def get_content(self):
        element = self.xget('atom:content|atom03:content')
        if element is not None:
            return inner_html(element)
        else:
            return ""

    def set_content(self, value):
        if not value:
            return self.xdel('atom:content|atom03:content')

        table = {'atom:feed': 'atom:content',
                 'atom03:feed': 'atom03:content'}
        element = self.xget_create(table)
        if element.attrib.get('type', '') == 'xhtml':
            clean_node(element)
        element.attrib['type'] = 'html'
        element.text = value

    def get_id(self):
        return self.xval('atom:id|atom03:id')

    def set_id(self, value):
        if not value:
            return self.xdel('atom:id|atom03:id')

        table = {'atom:feed': 'atom:id',
                 'atom03:feed': 'atom03:id'}
        element = self.xget_create(table)
        element.text = value

    def get_time(self):
        return self.xval('atom:published|atom03:published')

    def set_time(self, value):
        if not value:
            return self.xdel('atom:published|atom03:published')

        table = {'atom:feed': 'atom:published',
                 'atom03:feed': 'atom03:published'}
        element = self.xget_create(table)
        element.text = value

    def get_updated(self):
        return self.xval('atom:updated|atom03:updated')

    def set_updated(self, value):
        if not value:
            return self.xdel('atom:updated|atom03:updated')

        table = {'atom:feed': 'atom:updated',
                 'atom03:feed': 'atom03:updated'}
        element = self.xget_create(table)
        element.text = value
