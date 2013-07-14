#!/usr/bin/env python

from lxml import etree
import re

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
	doc = etree.fromstring(data)
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
			return match.text
		else:
			return ""

	def xgetCreate(self, table):
		""" Returns an element, and creates it when not present """
		tag = table[self.tag]
		match = self.xget(tag)
		if match is not None:
			return match
		else:
			element = etree.Element(tagNS(tag))
			self.root.append(element)
			return element

	def tostring(self, **k):
		""" Returns string using lxml. Arguments passed to tostring """
		return etree.tostring(self.xml, pretty_print=True, **k)

class FeedParser(FeedBase):
	FeedItem = 'FeedItem'
	mimetype = 'application/xml'

	def __init__(self, xml, tag):
		self.xml = xml
		self.root = self.xml.xpath("//atom03:feed|//atom:feed|//channel|//rssfake:channel", namespaces=NSMAP)[0]
		self.tag = tag
		self._items = {} # id(xml) => FeedItem

	def getTitle(self):
		return ""

	def setTitle(self, value):
		pass


	def getDesc(self):
		pass

	def setDesc(self, value):
		pass


	def getItems(self):
		return []

	def setItems(self, value):
		pass

	title = property(
		fget=lambda self:	self.getTitle(),
		fset=lambda self,v: self.setTitle(v))
	description = desc = property(
		fget=lambda self:	self.getDesc(),
		fset=lambda self,v: self.setDesc(v))
	items = property(
		fget=lambda self:	self._getItems(),
		fset=lambda self,v: self.setItems(v))

	def _getItems(self):
		items = self.getItems()
		out = []
		for item in items:
			if id(item) in self._items:
				out.append(self._items[id(item)])
			else:
				new = eval(self.FeedItem)(item, self.tag)
				self._items[id(item)] = new
				out.append(new)
		return out

	def __getitem__(self, key):
		return self.items[key]

	def __delitem__(self, key):
		item = self.getItems()[key]
		if id(item) in self._items:
			self._items[id(item)].remove()
			del self._items[id(item)]
		else:
			item.getparent().remove(item)

	def __len__(self):
		return len(self.getItems())

class FeedParserRSS(FeedParser):
	"""
	RSS Parser
	"""
	FeedItem = 'FeedItemRSS'
	mimetype = 'application/rss+xml'

	def getTitle(self):
		return self.xval('rssfake:title|title')

	def setTitle(self, value):
		table = {	'rdf:rdf':	'rssfake:title',
					'channel':	'title'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		return self.xval('rssfake:description|description')

	def setDesc(self, value):
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
	FeedItem = 'FeedItemAtom'
	mimetype = 'application/atom+xml'

	def getTitle(self):
		return self.xval('atom:title|atom03:title')

	def setTitle(self, value):
		table = {	'atom:feed':	'atom:title',
					'atom03:feed':	'atom03:title'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		return self.xval('atom:subtitle|atom03:subtitle')

	def setDesc(self, value):
		table = {	'atom:feed':	'atom:subtitle',
					'atom03:feed':	'atom03:subtitle'}
		element = self.xgetCreate(table)
		element.text = value


	def getItems(self):
		return self.xpath('atom:entry|atom03:entry')

class FeedItem(FeedBase):
	def __init__(self, xml, tag):
		self.root = self.xml = xml
		self.tag = tag

	def getTitle(self):
		return ""

	def setTitle(self):
		pass


	def getDesc(self):
		return ""

	def setDesc(self, value):
		pass


	def getContent(self):
		return ""

	def setContent(self, value):
		pass


	title = property(
		fget=lambda self:	self.getTitle(),
		fset=lambda self,v: self.setTitle(v))
	link = property(
		fget=lambda self:	self.getLink(),
		fset=lambda self,v: self.setLink(v))
	description = desc = property(
		fget=lambda self:	self.getDesc(),
		fset=lambda self,v: self.setDesc(v))
	content = property(
		fget=lambda self:	self.getContent(),
		fset=lambda self,v: self.setContent(v))

	def remove(self):
		self.xml.getparent().remove(self.xml)

class FeedItemRSS(FeedItem):
	def getTitle(self):
		return self.xval('rssfake:title|title')

	def setTitle(self, value):
		table = {	'rdf:rdf':	'rssfake:title',
					'channel':	'title'}
		element = self.xgetCreate(table)
		element.text = value


	def getLink(self):
		return self.xval('rssfake:link|link')

	def setLink(self, value):
		table = {	'rdf:rdf':	'rssfake:link',
					'channel':	'link'}
		element = self.xgetCreate(table)
		element.text = value


	def getDesc(self):
		return self.xval('rssfake:description|description')

	def setDesc(self, value):
		table = {	'rdf:rdf':	'rssfake:description',
					'channel':	'description'}
		element = self.xgetCreate(table)
		element.text = value


	def getContent(self):
		return self.xval('content:encoded')

	def setContent(self, value):
		table = {	'rdf:rdf':	'content:encoded',
					'channel':	'content:encoded'}
		element = self.xgetCreate(table)
		element.text = value

class FeedItemAtom(FeedItem):
	def getTitle(self):
		return self.xval('atom:title|atom03:title')

	def setTitle(self, value):
		table = {	'atom:feed':	'atom:title',
					'atom03:feed':	'atom03:title'}
		element = self.xgetCreate(table)
		element.text = value


	def getLink(self):
		return self.xget('atom:link|atom03:link').get('href', '')

	def setLink(self, value):
		table = {	'atom:feed':	'atom:link',
					'atom03:feed':	'atom03:link'}
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
		table = {	'atom:feed':	'atom:content',
					'atom03:feed':	'atom03:content'}
		element = self.xgetCreate(table)
		if element.attrib.get('type', '') == 'xhtml':
			cleanNode(element)
		element.attrib['type'] = 'html'
		element.text = value
