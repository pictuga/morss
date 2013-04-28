#!/usr/bin/env python
import sys
import os
import os.path
import time

from base64 import b64encode, b64decode
import re
import string

import lxml.etree
import lxml.objectify
import lxml.html
import lxml.html.clean
import lxml.builder

import urllib2
from cookielib import CookieJar
import chardet

from readability import readability

SERVER = True
MAX = 70
DELAY=10

ITEM_MAP = {
	'link':		(('{http://www.w3.org/2005/Atom}link', 'href'),	'{}link'),
	'desc':		('{http://www.w3.org/2005/Atom}summary',	'{}description'),
	'description':	('{http://www.w3.org/2005/Atom}summary',	'{}description'),
	'summary':	('{http://www.w3.org/2005/Atom}summary',	'{}description'),
	'content':	('{http://www.w3.org/2005/Atom}content',	'{http://purl.org/rss/1.0/modules/content/}encoded')
	}
RSS_MAP = {
	'desc':		('{http://www.w3.org/2005/Atom}subtitle',	'{}description'),
	'description':	('{http://www.w3.org/2005/Atom}subtitle',	'{}description'),
	'subtitle':	('{http://www.w3.org/2005/Atom}subtitle',	'{}description'),
	'item':		('{http://www.w3.org/2005/Atom}entry',		'{}item'),
	'entry':	('{http://www.w3.org/2005/Atom}entry',		'{}item')
	}

if 'REQUEST_URI' in os.environ:
	import httplib
	httplib.HTTPConnection.debuglevel = 1

	import cgitb
	cgitb.enable()

def log(txt):
	if not 'REQUEST_URI' in os.environ:
		if os.getenv('DEBUG', False):
			print txt
	else:
		with open('morss.log', 'a') as file:
			file.write(repr(txt).encode('utf-8') + "\n")

def cleanXML(xml):
	table = string.maketrans('', '')
	return xml.translate(table, table[:32]).lstrip()

class Cache:
	"""Light, error-prone caching system."""
	def __init__(self, folder, key):
		self._key = key
		self._dir = folder
		self._file = self._dir + "/" + str(hash(self._key))
		self._new = not os.path.exists(self._file)
		self._cached = {} # what *was* cached
		self._cache = {} # new things to put in cache

		if not self._new:
			data = open(self._file).read().strip().split("\n")
			for line in data:
				key, bdata = line.split("\t")
				self._cached[key] = bdata

		log(str(hash(self._key)))

	def __del__(self):
		self.save()

	def __contains__(self, key):
		return key in self._cached

	def get(self, key):
		if key in self._cached:
			self._cache[key] = self._cached[key]
			return b64decode(self._cached[key])
		else:
			return None

	def set(self, key, content):
		self._cache[key] = b64encode(content)

		if self._new:
			self.save()

	def save(self):
		if len(self._cache) == 0:
			return

		txt = ""
		for (key, bdata) in self._cache.iteritems():
			txt += "\n" + str(key) + "\t" + bdata
		txt.strip()

		if not os.path.exists(self._dir):
			os.makedirs(self._dir)

		open(self._file, 'w').write(txt)

	def isYoungerThan(self, sec):
		if not os.path.exists(self._file):
			return False

		return os.path.getmtime(self._file) > time.time()-sec

class XMLMap(object):
	"""
	Sort of wrapper around lxml.objectify.StringElement (from which this
	class *DOESN'T* inherit) which makes "links" between different children
	of an element. For example, this allows cheap, efficient, transparent
	RSS 2.0/Atom seamless use, which can be way faster than feedparser, and
	has the advantage to edit the corresponding mapped fields. On top of
	that, XML output with "classic" lxml API calls (such as
	lxml.etree.tostring) is still possible. Element attributes are also
	supported (as in <entry attr='value'/>).

	However, keep in mind that this feature's support is only partial. For
	example if you want to alias an element to both <el>value</el> and <el
	href='value'/>, and put them as ('el', ('el', 'value')) in the _map
	definition, then only 'el' will be whatched, even if ('el', 'value')
	makes more sens in that specific case, because that would require to
	also check the others, in case of "better" match, which is not done now.

	Also, this class assumes there's some consistency in the _map
	definition. Which means that it expects matches to be always found in
	the same "column" in _map. This is useful when setting values which are
	not yet in the XML tree. Indeed the class will try to use the alias from
	the same column. With the RSS/Atom example, the default _map will always
	create elements for the same kind of feed.
	"""
	def __init__(self, obj, alias=ITEM_MAP, string=False):
		self._xml = obj
		self._key = None
		self._map = alias
		self._str = string

		self._guessKey()

	def _guessKey(self):
		for tag in self._map:
			self._key = 0
			for choice in self._map[tag]:
				if not isinstance(choice, tuple):
					choice = (choice, None)
				el, attr = choice
				if hasattr(self._xml, el):
					if attr is None:
						return
					else:
						if attr in self._xml[el].attrib:
							return
				self._key+=1
		self._key = 0

	def _getElement(self, tag):
		"""Returns a tuple whatsoever."""
		if tag in self._map:
			for choice in self._map[tag]:
				if not isinstance(choice, tuple):
					choice = (choice, None)
				el, attr = choice
				if hasattr(self._xml, el):
					if attr is None:
						return (self._xml[el], attr)
					else:
						if attr in self._xml[el].attrib:
							return (self._xml[el], attr)
			return (None, None)
		if hasattr(self._xml, tag):
			return (self._xml[tag], None)
		return (None, None)

	def __getattr__(self, tag):
		el, attr = self._getElement(tag)
		if el is not None:
			if attr is None:
				out = el
			else:
				out = el.get(attr)
		else:
			out = self._xml.__getattr__(tag)

		return unicode(out) if self._str else out

	def __getitem__(self, tag):
		return self.__getattr__(tag)

	def __setattr__(self, tag, value):
		if tag.startswith('_'):
			return object.__setattr__(self, tag, value)

		el, attr = self._getElement(tag)
		if el is not None:
			if attr is None:
				if (isinstance(value, lxml.objectify.StringElement)
					or isinstance(value, str)
					or isinstance(value, unicode)):
					el._setText(value)
				else:
					el = value
				return
			else:
				el.set(attr, value)
				return
		choice = self._map[tag][self._key]
		if not isinstance(choice, tuple):
			child = lxml.objectify.Element(choice)
			self._xml.append(child)
			self._xml[choice] = value
			return
		else:
			el, attr = choice
			child = lxml.objectify.Element(choice, attrib={attr:value})
			self._xml.append(child)
			return

	def __contains__(self, tag):
		el, attr = self._getElement(tag)
		return el is not None

	def remove(self):
		self._xml.getparent().remove(self._xml)

	def tostring(self, **k):
		"""Returns string using lxml. Arguments passed to tostring."""
		out = self._xml if self._xml.getparent() is None else self._xml.getparent()
		return lxml.etree.tostring(out, pretty_print=True, **k)

def EncDownload(url):
	try:
		cj = CookieJar()
		opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
		con = opener.open(url)
		data = con.read()
	except (urllib2.HTTPError, urllib2.URLError) as error:
		log(error)
		log('http error')
		return False

	# meta-redirect
	match = re.search(r'(?i)<meta http-equiv=.refresh[^>]*?url=(http.*?)["\']', data)
	if match:
		new_url = match.groups()[0]
		log('redirect: %s' % new_url)
		return EncDownload(new_url)

	# encoding
	if con.headers.getparam('charset'):
		log('header')
		enc = con.headers.getparam('charset')
	else:
		match = re.search('charset=["\']?([0-9a-zA-Z-]+)', data).groups()
		if len(match):
			log('meta.re')
			enc = match[0]
		else:
			log('chardet')
			enc = chardet.detect(data)['encoding']

	return (data, enc, con.geturl())

def Fill(rss, cache):
	item = XMLMap(rss, ITEM_MAP, True)
	log(item.link)

	if 'link' not in item:
		log('no link')
		return

	# content already provided?
	if 'content' in item and 'desc' in item:
		content_len = len(lxml.html.fromstring(item.content).text_content())
		log('content: %s vs %s' % (content_len, len(item.desc)))
		if content_len > 5*len(item.desc):
			log('provided')
			return

	match = re.search('/([0-9a-zA-Z]{20,})/story01.htm$', item.link)
	if match:
		url = match.groups()[0].split('0')
		t = {'A':'0', 'B':'.', 'C':'/', 'D':'?', 'E':'-', 'I':'_', 'L':'http://', 'S':'www.', 'N':'.com', 'O':'.co.uk'}
		item.link = "".join([(t[s[0]] if s[0] in t else "=") + s[1:] for s in url[1:]])
		log(item.link)
	if '{http://rssnamespace.org/feedburner/ext/1.0}origLink' in item:
		item.link = item['{http://rssnamespace.org/feedburner/ext/1.0}origLink']
		log(item.link)

	# check cache
	if item.link in cache:
		log('cached')
		item.content = cache.get(item.link)
		return

	# download
	ddl = EncDownload(item.link)

	if ddl is False:
		return item

	data, enc, url = ddl
	log(enc)

	out = readability.Document(data.decode(enc, 'ignore'), url=url).summary(True)

	item.content = out
	cache.set(item.link, out)

def Gather(url, cachePath):
	cache = Cache(cachePath, url)

	# fetch feed
	if cache.isYoungerThan(DELAY*60) and url in cache:
		log('xml cached')
		xml = cache.get(url)
	else:
		try:
			req = urllib2.Request(url)
			req.add_unredirected_header('User-Agent', 'Liferea/1.8.12 (Linux; fr_FR.utf8; http://liferea.sf.net/)')
			xml = urllib2.urlopen(req).read()
			cache.set(url, xml)
		except (urllib2.HTTPError, urllib2.URLError):
			print "Error, couldn't fetch RSS feed (the server might be banned from the given website)."
			return False

	xml = cleanXML(xml)
	rss = lxml.objectify.fromstring(xml)
	root = rss.channel if hasattr(rss, 'channel') else rss
	root = XMLMap(root, RSS_MAP)

	# set
	if MAX:
		for item in root.item[MAX:]:
			item.getparent().remove(item)
	for item in root.item:
		Fill(item, cache)

	return root.tostring(xml_declaration=True, encoding='UTF-8')

if __name__ == "__main__":
	if 'REQUEST_URI' in os.environ:
		print 'Status: 200'
		print 'Content-Type: text/html\n'

		if 'REDIRECT_URL' in os.environ:
			url = os.environ['REQUEST_URI'][1:]
		else:
			url = os.environ['REQUEST_URI'][len(os.environ['SCRIPT_NAME'])+1:]
		if not url.startswith('http://') and not url.startswith('https://'):
			url = "http://" + url
		url = url.replace(' ', '%20')

		cache = os.getcwd() + '/cache'
		log(url)
		RSS = Gather(url, cache)
	else:
		if len(sys.argv) > 1 and sys.argv[1].startswith('http'):
			url = sys.argv[1]
			cache =	os.path.expanduser('~') + '/.cache/morss'
			RSS = Gather(url, cache)
		else:
			print "Please provide url."
			sys.exit(1)

	if 'REQUEST_URI' in os.environ or not os.getenv('DEBUG', False) and RSS is not False:
		print RSS

	log('done')
