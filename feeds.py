#!/usr/bin/env python

from lxml import etree
from datetime import datetime
import dateutil.parser
from dateutil import tz
import re

Element = etree.Element

NSMAP = {'atom':	'http://www.w3.org/2005/Atom',
	'atom03':	'http://purl.org/atom/ns#',
	'media':	'http://search.yahoo.com/mrss/',
	'rdf':		'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
	'slash':	'http://purl.org/rss/1.0/modules/slash/',
	'dc':		'http://purl.org/dc/elements/1.1/',
	'content':	'http://purl.org/rss/1.0/modules/content/',
	'rssfake':	'http://purl.org/rss/1.0/'}

def load(url):
	import urllib2
	d = urllib2.urlopen(url).read()
	return parse(d)

def tagNS(tag, nsmap=NSMAP):
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

def innerHTML(xml):
	return (xml.text or '') + ''.join([etree.tostring(child) for child in xml.iterchildren()])

def cleanNode(xml):
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
		mtable = {	'rdf:rdf': FeedParserRSS, 'channel': FeedParserRSS,
					'atom03:feed': FeedParserAtom, 'atom:feed': FeedParserAtom }
		match = match[0]
		tag = tagNS(match.tag)
		if tag in mtable:
			return mtable[tag](doc, tag)

	raise FeedException('unknow feed type')

class FeedBase(object):
	"""
	Base for xml-related classes, which provides simple wrappers around xpath
	selection and item creation
	"""
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

	def xgetCreate(self, table):
		""" Returns an element, and creates it when not present """
		value = table[self.tag]
		if not isinstance(value, tuple):
			value = (value, value)
		new, xpath = value
		match = self.xget(xpath)
		if match is not None:
			return match
		else:
			element = etree.Element(tagNS(new))
			self.root.append(element)
			return element

	def xdel(self, path):
		match = self.xget(path)
		if match is not None:
			return match.getparent().remove(match)

	def tostring(self, **k):
		""" Returns string using lxml. Arguments passed to tostring """
		return etree.tostring(self.xml, pretty_print=True, **k)

class FeedDescriptor(object):
	"""
	Descriptor which gives off elements based on "self.getName" and
	"self.setName" as getter/setters. Looks far better, and avoids duplicates
	"""
	def __init__(self, name):
		self.name = name
		self.nname = name[0].upper() + name[1:]

	def __get__(self, instance, owner):
		getter = getattr(instance, 'get%s' % self.nname)
		return getter()

	def __set__(self, instance, value):
		setter = getattr(instance, 'set%s' % self.nname)
		return setter(value)

	def __delete__(self, instance):
		deleter = getattr(instance, 'del%s' % self.nname)
		return deleter()

class FeedTime(FeedDescriptor):
	def __get__(self, instance, owner):
		getter = getattr(instance, 'get%s' % self.nname)
		raw = getter()
		try:
			time = parseTime(raw)
			return time
		except ValueError:
			return None

	def __set__(self, instance, value):
		try:
			time = parseTime(value)
			raw = time.strftime(instance.timeFormat)
			setter = getattr(instance, 'set%s' % self.nname)
			return setter(raw)
		except ValueError:
			pass

class FeedBool(FeedDescriptor):
	def __get__(self, instance, owner):
		getter = getattr(instance, 'get%s' % self.nname)
		raw = getter()
		return (raw or '').lower() != 'false'

	def __set__(self, instance, value):
		raw = 'true' if value else 'false'
		setter = getattr(instance, 'set%s' % self.nname)
		return setter(raw)

def parseTime(value):
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

class FeedList(object):
	"""
	Class to map a list of xml elements against a list of matching objects,
	while avoiding to recreate the same matching object over and over again. So
	as to avoid extra confusion, list's elements are called "children" here, so
	as not to use "items", which is already in use in RSS/Atom related code.

	Comes with its very own descriptor.
	"""
	def __init__(self, parent, getter, tag, childClass):
		self.parent = parent
		self.getter = getter
		self.childClass = childClass
		self.tag = tag
		self._children = {} # id(xml) => FeedItem

	def getChildren(self):
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
		return self.getChildren()[key]

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
		self.items = {} # id(instance) => FeedList

	def __get__(self, instance, owner=None):
		key = id(instance)
		if key in self.items:
			return self.items[key]
		else:
			getter = getattr(instance, 'get%s' % self.name.title())
			className = globals()[getattr(instance, '%sClass' % self.name)]
			self.items[key] = FeedList(instance, getter, instance.tag, className)
			return self.items[key]

	def __set__(self, instance, value):
		feedlist = self.__get__(instance)
		[x.remove() for x in [x for x in f.items]]
		[feedlist.append(x) for x in value]

class FeedParser(FeedBase):
	itemsClass = 'FeedItem'
	mimetype = 'application/xml'
	base = '<?xml?>'

	def __init__(self, xml=None, tag='atom:feed'):
		if xml is None:
			xml = etree.fromstring(self.base[tag])
		self.xml = xml
		self.root = self.xml.xpath("//atom03:feed|//atom:feed|//channel|//rssfake:channel", namespaces=NSMAP)[0]
		self.tag = tag

	def getTitle(self):
		return ""

	def setTitle(self, value):
		pass

	def delTitle(self):
		self.title = ""


	def getDesc(self):
		pass

	def setDesc(self, value):
		pass

	def delDesc(self):
		self.desc = ""


	def getItems(self):
		return []

	title = FeedDescriptor('title')
	description = desc = FeedDescriptor('desc')
	items = FeedListDescriptor('items')

	def tostring(self, **k):
		return etree.tostring(self.xml.getroottree(), pretty_print=True, **k)

class FeedParserRSS(FeedParser):
	"""
	RSS Parser
	"""
	itemsClass = 'FeedItemRSS'
	mimetype = 'application/rss+xml'
	base = {	'rdf:rdf':	'<?xml version="1.0" encoding="utf-8"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><channel rdf:about="http://example.org/rss.rdf"></channel></rdf:RDF>',
				'channel':	'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel></channel></rss>'}

	def getTitle(self):
		return self.xval('rssfake:title|title')

	def setTitle(self, value):
		if not value:
			return self.xdel('rssfake:title|title')

		table = {	'rdf:rdf':	'rssfake:title',
					'channel':	'title'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		print 'YEAH'
		return self.xval('rssfake:description|description')

	def setDesc(self, value):
		if not value:
			return self.xdel('rssfake:description|description')

		table = {	'rdf:rdf':	'rssfake:description',
					'channel':	'description'}
		element = self.xgetCreate(table)
		element.text = value


	def getItems(self):
		return self.xpath('rssfake:item|item')

class FeedParserAtom(FeedParser):
	"""
	Atom Parser
	"""
	itemsClass = 'FeedItemAtom'
	mimetype = 'application/atom+xml'
	base = {	'atom:feed':	'<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
				'atom03:feed':	'<?xml version="1.0" encoding="utf-8"?><feed version="0.3" xmlns="http://purl.org/atom/ns#"></feed>'}

	def getTitle(self):
		return self.xval('atom:title|atom03:title')

	def setTitle(self, value):
		if not value:
			return self.xval('atom:title|atom03:title')

		table = {	'atom:feed':	'atom:title',
					'atom03:feed':	'atom03:title'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		return self.xval('atom:subtitle|atom03:subtitle')

	def setDesc(self, value):
		if not value:
			return self.xdel('atom:subtitle|atom03:subtitle')

		table = {	'atom:feed':	'atom:subtitle',
					'atom03:feed':	'atom03:subtitle'}
		element = self.xgetCreate(table)
		element.text = value


	def getItems(self):
		return self.xpath('atom:entry|atom03:entry')

class FeedItem(FeedBase):
	timeFormat = ''

	def __init__(self, xml=None, tag='atom:feed'):
		if xml is None:
			xml = Element(tagNS(self.base[tag]))

		self.root = self.xml = xml
		self.tag = tag

	def getTitle(self):
		return ""

	def setTitle(self):
		pass

	def delTitle(self):
		self.title = ""


	def getLink(self):
		return ""

	def setLink(self, value):
		pass

	def delLink(self):
		pass


	def getIsPermaLink(self):
		return ""

	def setIsPermaLink(self, value):
		pass


	def getDesc(self):
		return ""

	def setDesc(self, value):
		pass

	def delDesc(self):
		self.desc = ""


	def getContent(self):
		return ""

	def setContent(self, value):
		pass

	def delContent(self):
		self.content = ""


	def getId(self):
		return ""

	def setId(self, value):
		pass

	def delId(self):
		self.id = ""


	def getTime(self):
		return None

	def setTime(self, value):
		pass

	def delTime(self):
		self.time = None


	def getUpdated(self):
		return None

	def setUpdated(self, value):
		pass

	def delUpdated(self):
		self.updated = None

	title = FeedDescriptor('title')
	link = FeedDescriptor('link')
	description = desc = FeedDescriptor('desc')
	content = FeedDescriptor('content')
	id = FeedDescriptor('id')
	isPermaLink = FeedBool('isPermaLink')
	time = FeedTime('time')
	updated = FeedTime('updated')

	def pushContent(self, value):
		if not self.desc and self.content:
			self.desc = self.content

		self.content = value

	def remove(self):
		self.xml.getparent().remove(self.xml)

class FeedItemRSS(FeedItem):
	timeFormat = '%a, %d %b %Y %H:%M:%S %Z'
	base =  {	'rdf:rdf':	'rssfake:item',
				'channel':	'item'}

	def getTitle(self):
		return self.xval('rssfake:title|title')

	def setTitle(self, value):
		if not value:
			return self.xdel('rssfake:title|title')

		table = {	'rdf:rdf':	'rssfake:title',
					'channel':	'title'}
		element = self.xgetCreate(table)
		element.text = value


	def getLink(self):
		return self.xval('rssfake:link|link')

	def setLink(self, value):
		if self.isPermaLink and self.id == self.link != value:
			self.isPermaLink = False

		table = {	'rdf:rdf':	'rssfake:link',
					'channel':	'link'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		return self.xval('rssfake:description|description')

	def setDesc(self, value):
		if not value:
			return self.xdel('rssfake:description|description')

		table = {	'rdf:rdf':	'rssfake:description',
					'channel':	'description'}
		element = self.xgetCreate(table)
		element.text = value


	def getContent(self):
		return self.xval('content:encoded')

	def setContent(self, value):
		if not value:
			return self.xdel('content:encoded')

		table = {	'rdf:rdf':	'content:encoded',
					'channel':	'content:encoded'}
		element = self.xgetCreate(table)
		element.text = value


	def getId(self):
		return self.xval('rssfake:guid|guid')

	def setId(self, value):
		if not value:
			return self.xdel('rssfake:guid|guid')

		table = {	'rdf:rdf':	'rssfake:guid',
					'channel':	'guid'}
		element = self.xgetCreate(table)
		element.text = value


	def getIsPermaLink(self):
		return self.xget('rssfake:guid/@isPermaLink|guid/@isPermaLink')

	def setIsPermaLink(self, value):
		table = {	'rdf:rdf':	'rssfake:guid',
					'channel':	'guid'}
		element = self.xgetCreate(table)
		element.attrib['isPermaLink'] = value


	def getTime(self):
		return self.xval('rssfake:pubDate|pubDate')

	def setTime(self, value):
		if not value:
			return self.xdel('rssfake:pubDate|pubDate')

		table = {	'rdf:rdf':	'rssfake:pubDate',
					'channel':	'pubDate'}
		element = self.xgetCreate(table)
		element.text = value

class FeedItemAtom(FeedItem):
	timeFormat = '%Y-%m-%dT%H:%M:%SZ'
	base = {	'atom:feed':	'atom:entry',
				'atom03:feed':	'atom03:entry'}

	def getTitle(self):
		return self.xval('atom:title|atom03:title')

	def setTitle(self, value):
		if not value:
			return self.xdel('atom:title|atom03:title')

		table = {	'atom:feed':	'atom:title',
					'atom03:feed':	'atom03:title'}
		element = self.xgetCreate(table)
		element.text = value


	def getLink(self):
		return self.xget('(atom:link|atom03:link)[@rel="alternate" or not(@rel)]/@href')

	def setLink(self, value):
		table = {	'atom:feed':	('atom:link', 'atom:link[@rel="alternate" or not(@rel)]'),
					'atom03:feed':	('atom03:link', 'atom03:link[@rel="alternate" or not(@rel)]')}
		element = self.xgetCreate(table)
		element.attrib['href'] = value


	def getDesc(self):
		# default "type" is "text"
		element = self.xget('atom:summary|atom03:summary')
		if element is not None:
			return innerHTML(element)
		else:
			return ""

	def setDesc(self, value):
		if not value:
			return self.xdel('atom:summary|atom03:summary')

		table = {	'atom:feed':	'atom:summary',
					'atom03:feed':	'atom03:summary'}
		element = self.xgetCreate(table)
		if element.attrib.get('type', '') == 'xhtml':
			cleanNode(element)
		element.attrib['type'] = 'html'
		element.text = value


	def getContent(self):
		element = self.xget('atom:content|atom03:content')
		if element is not None:
			return innerHTML(element)
		else:
			return ""

	def setContent(self, value):
		if not value:
			return self.xdel('atom:content|atom03:content')

		table = {	'atom:feed':	'atom:content',
					'atom03:feed':	'atom03:content'}
		element = self.xgetCreate(table)
		if element.attrib.get('type', '') == 'xhtml':
			cleanNode(element)
		element.attrib['type'] = 'html'
		element.text = value


	def getId(self):
		return self.xval('atom:id|atom03:id')

	def setId(self, value):
		if not value:
			return self.xdel('atom:id|atom03:id')

		table = {	'atom:feed':	'atom:id',
					'atom03:feed':	'atom03:id'}
		element = self.xgetCreate(table)
		element.text = value


	def getTime(self):
		return self.xval('atom:published|atom03:published')

	def setTime(self, value):
		if not value:
			return self.xdel('atom:published|atom03:published')

		table = {	'atom:feed':	'atom:published',
					'atom03:feed':	'atom03:published'}
		element = self.xgetCreate(table)
		element.text = value


	def getUpdated(self):
		return self.xval('atom:updated|atom03:updated')

	def setUpdated(self, value):
		if not value:
			return self.xdel('atom:updated|atom03:updated')

		table = {	'atom:feed':	'atom:updated',
					'atom03:feed':	'atom03:updated'}
		element = self.xgetCreate(table)
		element.text = value
