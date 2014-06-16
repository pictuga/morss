#!/usr/bin/env python

from datetime import datetime
from StringIO import StringIO

import re
import json
import csv
import urllib2

from lxml import etree
from dateutil import tz
import dateutil.parser

try:
    from wheezy.template.engine import Engine
    from wheezy.template.loader import DictLoader
    from wheezy.template.ext.core import CoreExtension
except ImportError:
    Engine = DictLoader = CoreExtension = None

json.encoder.c_make_encoder = None

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

Element = etree.Element

NSMAP = {'atom': 'http://www.w3.org/2005/Atom',
         'atom03': 'http://purl.org/atom/ns#',
         'media': 'http://search.yahoo.com/mrss/',
         'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
         'slash': 'http://purl.org/rss/1.0/modules/slash/',
         'dc': 'http://purl.org/dc/elements/1.1/',
         'content': 'http://purl.org/rss/1.0/modules/content/',
         'rssfake': 'http://purl.org/rss/1.0/'}


def camel_case_to_underscore(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def load(url):
    d = urllib2.urlopen(url).read()
    return parse(d)


def tag_NS(tag, nsmap=NSMAP):
    match = re.search(r'^\{([^\}]+)\}(.*)$', tag)
    if match:
        match = match.groups()
        for (key, url) in nsmap.iteritems():
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
    return (xml.text or '') + ''.join([etree.tostring(child) for child in xml.iterchildren()])


def clean_node(xml):
    [xml.remove(child) for child in xml.iterchildren()]


class FeedException(Exception):
    pass


def parse(data):
    # encoding
    match = re.search('encoding=["\']?([0-9a-zA-Z-]+)', data[:100])
    if match:
        enc = match.groups()[0].lower()
        if not isinstance(data, unicode):
            data = data.decode(enc, 'ignore')
        data = data.encode(enc)

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

    root = None
    xml = None
    tag = None
    base = None

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        setattr(self, item, value)

    def __delitem__(self, item):
        delattr(self, item)

    def __iter__(self):
        for element in self.__dict__:
            value = self[element]

            if isinstance(value, FeedList):
                value = [OrderedDict(x) for x in value]
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

    def to_string(self, **k):
        """ Returns string using lxml. Arguments passed to tostring """
        return etree.tostring(self.xml, pretty_print=True, **k)


class FeedDescriptor(object):
    """
    Descriptor which gives off elements based on "self.getName" and
    "self.setName" as getter/setters. Looks far better, and avoids duplicates
    """

    def __init__(self, name):
        self.name = name
        self.proper_name = name[0].upper() + name[1:]

    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % camel_case_to_underscore(self.proper_name))
        return getter()

    def __set__(self, instance, value):
        setter = getattr(instance, 'set_%s' % camel_case_to_underscore(self.proper_name))
        return setter(value)

    def __delete__(self, instance):
        deleter = getattr(instance, 'del_%s' % camel_case_to_underscore(self.proper_name))
        return deleter()


class FeedTime(FeedDescriptor):
    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % camel_case_to_underscore(self.proper_name))
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
            setter = getattr(instance, 'set_%s' % camel_case_to_underscore(self.proper_name))
            return setter(raw)
        except ValueError:
            pass


class FeedBool(FeedDescriptor):
    def __get__(self, instance, owner):
        getter = getattr(instance, 'get_%s' % camel_case_to_underscore(self.proper_name))
        raw = getter()
        return (raw or '').lower() != 'false'

    def __set__(self, instance, value):
        raw = 'true' if value else 'false'
        setter = getattr(instance, 'set_%s' % camel_case_to_underscore(self.proper_name))
        return setter(raw)


def parse_time(value):
    if isinstance(value, unicode) or isinstance(value, str):
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


class FeedList(object):
    """
    Class to map a list of xml elements against a list of matching objects,
    while avoiding to recreate the same matching object over and over again. So
    as to avoid extra confusion, list's elements are called "children" here, so
    as not to use "items", which is already in use in RSS/Atom related code.

    Comes with its very own descriptor.
    """

    def __init__(self, parent, getter, tag, child_class):
        self.parent = parent
        self.getter = getter
        self.childClass = child_class
        self.tag = tag
        self._children = {}  # id(xml) => FeedItem

    def get_children(self):
        children = self.getter()
        out = []
        for child in children:
            if id(child) in self._children:
                out.append(self._children[id(child)])
            else:
                new = self.childClass(child, self.tag)
                self._children[id(child)] = new
                out.append(new)
        return out

    def append(self, cousin=None):
        new = self.childClass(tag=self.tag)
        self.parent.root.append(new.xml)
        self._children[id(new.xml)] = new

        if cousin is None:
            return new

        for key in self.childClass.__dict__:
            if key[:3] == 'set':
                attr = key[3:].lower()
                if hasattr(cousin, attr):
                    setattr(new, attr, getattr(cousin, attr))
                elif attr in cousin:
                    setattr(new, attr, cousin[attr])

        return new

    def __getitem__(self, key):
        return self.get_children()[key]

    def __delitem__(self, key):
        child = self.getter()[key]
        if id(child) in self._children:
            self._children[id(child)].remove()
            del self._children[id(child)]
        else:
            child.getparent().remove(child)

    def __len__(self):
        return len(self.getter())


class FeedListDescriptor(object):
    """
    Descriptor for FeedList
    """

    def __init__(self, name):
        self.name = name
        self.items = {}  # id(instance) => FeedList

    def __get__(self, instance, owner=None):
        key = id(instance)
        if key in self.items:
            return self.items[key]
        else:
            getter = getattr(instance, 'get_{0}'.format(camel_case_to_underscore(self.name.title())))
            class_name = globals()[getattr(instance, '%sClass' % camel_case_to_underscore(self.name))]
            self.items[key] = FeedList(instance, getter, instance.tag, class_name)
            return self.items[key]

    def __set__(self, instance, value):
        feedlist = self.__get__(instance)
        feedlist.clear()
        [feedlist.append(x) for x in value]


class FeedParser(FeedBase):
    itemsClass = 'FeedItem'
    mimetype = 'application/xml'
    base = '<?xml?>'
    dic = ('title', 'desc', 'items')
    title = FeedDescriptor('title') or ''
    desc = FeedDescriptor('desc') or ''
    items = FeedListDescriptor('items') or []

    def __init__(self, xml=None, tag='atom:feed'):
        if xml is None:
            xml = etree.fromstring(self.base[tag])
        self.xml = xml
        self.root = self.xml.xpath("//atom03:feed|//atom:feed|//channel|//rssfake:channel", namespaces=NSMAP)[0]
        self.tag = tag

    def get_title(self):
        return self.title

    def set_title(self, value):
        self.title = value

    def del_title(self):
        self.title = ""

    def get_desc(self):
        return self.desc

    def set_desc(self, value):
        self.desc = value

    def del_desc(self):
        self.desc = ""

    def get_items(self):
        return self.items

    def to_string(self, **k):
        return etree.tostring(self.xml.getroottree(), pretty_print=True, **k)

    def to_json(self, indent=None):
        return json.dumps(OrderedDict(self), indent=indent)

    def to_csv(self):
        out = StringIO()
        c = csv.writer(out, dialect=csv.excel)
        for item in self.items:
            row = [x[1].encode('utf-8') if isinstance(x[1], unicode) else x[1] for x in item if
                   isinstance(x[1], basestring)]
            c.writerow(row)
        out.seek(0)
        return out.read()

    def to_html(self):
        if DictLoader is None:
            raise ImportError('dep wheezy.template needed')

        loader = DictLoader({'reader': open('reader.html.template').read()})
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
        'rdf:rdf': '<?xml version="1.0" encoding="utf-8"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><channel rdf:about="http://example.org/rss.rdf"></channel></rdf:RDF>',
        'channel': '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel></channel></rss>'}

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
        return self.xval('rssfake:desc|desc')

    def set_desc(self, value):
        if not value:
            return self.xdel('rssfake:desc|desc')

        table = {'rdf:rdf': 'rssfake:desc',
                 'channel': 'desc'}
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
    base = {'atom:feed': '<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
            'atom03:feed': '<?xml version="1.0" encoding="utf-8"?><feed version="0.3" xmlns="http://purl.org/atom/ns#"></feed>'}

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


class FeedItem(FeedBase):
    timeFormat = ''
    dic = ('title', 'link', 'desc', 'content', 'id', 'isPermaLink', 'time', 'updated')
    title = FeedDescriptor('title')
    link = FeedDescriptor('link')
    desc = FeedDescriptor('desc')
    content = FeedDescriptor('content')
    id = FeedDescriptor('id')
    is_permalink = FeedBool('isPermaLink')
    time = FeedTime('time')
    updated = FeedTime('updated')

    def __init__(self, xml=None, tag='atom:feed'):
        if xml is None:
            xml = Element(tag_NS(self.base[tag]))

        self.root = self.xml = xml
        self.tag = tag

    def get_title(self):
        return self.title

    def set_title(self, value):
        self.title = value

    def del_title(self):
        self.title = ""

    def get_link(self):
        return self.link

    def set_link(self, value):
        self.link = value

    def del_link(self):
        self.link = ""

    def get_is_a_permalink(self):
        return self.is_permalink

    def set_is_a_permalink(self, value):
        self.is_permalink = value

    def get_desc(self):
        return self.desc

    def set_desc(self, value):
        self.desc = value

    def del_desc(self):
        self.desc = ""

    def get_content(self):
        return self.content

    def set_content(self, value):
        self.content = value

    def del_content(self):
        self.content = ""

    def get_id(self):
        return self.id

    def set_id(self, value):
        self.id = value

    def del_id(self):
        self.id = ""

    def get_time(self):
        return self.time

    def set_time(self, value):
        self.time = value

    def del_time(self):
        self.time = None

    def get_updated(self):
        return self.updated

    def set_updated(self, value):
        self.updated = value

    def del_updated(self):
        self.updated = None

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
        return self.xval('rssfake:desc|desc')

    def set_desc(self, value):
        if not value:
            return self.xdel('rssfake:desc|desc')

        table = {'rdf:rdf': 'rssfake:desc',
                 'channel': 'desc'}
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

    def get_is_a_permalink(self):
        return self.xget('rssfake:guid/@isPermaLink|guid/@isPermaLink')

    def set_is_a_permalink(self, value):
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
