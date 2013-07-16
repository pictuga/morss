#!/usr/bin/env python
import sys
import os
import os.path
import time

from base64 import b64encode, b64decode
import re
import string

import lxml.html
import lxml.html.clean
import lxml.builder

import feeds

import urllib2
import socket
import chardet
import urlparse

from gzip import GzipFile
from StringIO import StringIO

from readability import readability

LIM_ITEM = 100	# deletes what's beyond
MAX_ITEM = 50	# cache-only beyond
MAX_TIME = 7	# cache-only after
DELAY = 10	# xml cache
TIMEOUT = 2	# http timeout

OPTIONS = ['progress', 'cache']

UA_RSS = 'Liferea/1.8.12 (Linux; fr_FR.utf8; http://liferea.sf.net/)'
UA_HML = 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.6; en-US; rv:1.9.2.11) Gecko/20101012 Firefox/3.6.11'

PROTOCOL = ['http', 'https', 'ftp']

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
			print repr(txt)
	else:
		with open('morss.log', 'a') as file:
			file.write(repr(txt).encode('utf-8') + "\n")


def lenHTML(txt):
	if len(txt):
		return len(lxml.html.fromstring(txt).text_content())
	else:
		return 0

def countWord(txt):
	if len(txt):
		return len(lxml.html.fromstring(txt).text_content().split())
	else:
		return 0

def makeDesc(txt, length, suffix='...'):
	' '.join(txt.split()[:length]) + suffix

def setContent(item, txt):
	if not item.desc:
		if item.content:
			log('content alone')
			item.desc = item.content
			item.content = txt
		else:
			log('empty')
			item.desc = makeDesc(txt, 30)
			item.content = txt
	else:
		item.content = txt

def parseOptions(available):
	options = None
	if 'REQUEST_URI' in os.environ:
		if 'REDIRECT_URL' in os.environ:
			url = os.environ['REQUEST_URI'][1:]
		else:
			url = os.environ['REQUEST_URI'][len(os.environ['SCRIPT_NAME'])+1:]

		if urlparse.urlparse(url).scheme not in PROTOCOL:
			split = url.split('/', 1)
			if len(split) and split[0] in available:
				options = split[0]
				url = split[1]
			url = 'http://' + url

	else:
		if len(sys.argv) == 3:
			if sys.argv[1] in available:
				options = sys.argv[1]
			url = sys.argv[2]
		elif len(sys.argv) == 2:
			url = sys.argv[1]
		else:
			return (None, None)

		if urlparse.urlparse(url).scheme not in PROTOCOL:
			url = 'http://' + url

	return (url, options)

class Cache:
	"""Light, error-prone caching system."""
	def __init__(self, folder, key):
		self._key = key
		self._hash = str(hash(self._key))

		self._dir = folder
		self._file = self._dir + '/' + self._hash

		self._cached = {} # what *was* cached
		self._cache = {} # new things to put in cache

		if os.path.isfile(self._file):
			data = open(self._file).readlines()
			for line in data:
				if "\t" in line:
					key, bdata = line.split("\t", 1)
					self._cached[key] = bdata

		log(self._hash)

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

	def save(self):
		if len(self._cache) == 0:
			return

		out = []
		for (key, bdata) in self._cache.iteritems():
			out.append(str(key) + "\t" + bdata)
		txt = "\n".join(out)

		if not os.path.exists(self._dir):
			os.makedirs(self._dir)

		with open(self._file, 'w') as file:
			file.write(txt)

	def isYoungerThan(self, sec):
		if not os.path.exists(self._file):
			return False

		return time.time() - os.path.getmtime(self._file) < sec

class HTMLDownloader(urllib2.HTTPCookieProcessor):
	"""
	Custom urllib2 handler to download html pages, following <meta> redirects,
	using a browser user-agent and storing cookies.
	"""
	def __init__(self, cookiejar=None):
		urllib2.HTTPCookieProcessor.__init__(self, cookiejar)
		self.userAgent = UA_HML

	def http_request(self, req):
		urllib2.HTTPCookieProcessor.http_request(self, req)
		req.add_header('Accept-Encoding', 'gzip')
		return req

	def http_response(self, req, resp):
		urllib2.HTTPCookieProcessor.http_response(self, req, resp)

		if 200 <= resp.code < 300 and resp.info().maintype == 'text':
			data = resp.read()

			# gzip
			if resp.headers.get('Content-Encoding') == 'gzip':
				log('un-gzip')
				data = GzipFile(fileobj=StringIO(data), mode='r').read()

			# <meta> redirect
			match = re.search(r'(?i)<meta http-equiv=.refresh[^>]*?url=(http.*?)["\']', data)
			if match:
				newurl = match.groups()[0]
				log('redirect: %s' % newurl)

				newheaders = dict((k,v) for k,v in req.headers.items()
					if k.lower() not in ('content-length', 'content-type'))
				new = urllib2.Request(newurl,
					headers=newheaders,
					origin_req_host=req.get_origin_req_host(),
					unverifiable=True)

				return self.parent.open(new, timeout=req.timeout)

			# decode
			data = decodeHTML(resp, data)

			fp = StringIO(data)
			old_resp = resp
			resp = urllib2.addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
			resp.msg = old_resp.msg
		return resp

	https_response = http_response
	https_request = http_request

def decodeHTML(con, data):
	if con.headers.getparam('charset'):
		log('header')
		enc = con.headers.getparam('charset')
	else:
		match = re.search('charset=["\']?([0-9a-zA-Z-]+)', data)
		if match:
			log('meta.re')
			enc = match.groups()[0]
		else:
			log('chardet')
			enc = chardet.detect(data)['encoding']

	log(enc)
	return data.decode(enc, 'replace')

def Fill(item, cache, feedurl='/', fast=False):
	""" Returns True when it has done its best """

	if not item.link:
		log('no link')
		return True

	log(item.link)

	# feedburner
	feeds.NSMAP['feedburner'] = 'http://rssnamespace.org/feedburner/ext/1.0'
	match = item.xval('feedburner:origLink')
	if match:
		item.link = match
		log(item.link)

	# feedsportal
	match = re.search('/([0-9a-zA-Z]{20,})/story01.htm$', item.link)
	if match:
		url = match.groups()[0].split('0')
		t = {'A':'0', 'B':'.', 'C':'/', 'D':'?', 'E':'-', 'I':'_', 'L':'http://', 'S':'www.', 'N':'.com', 'O':'.co.uk'}
		item.link = ''.join([(t[s[0]] if s[0] in t else '=') + s[1:] for s in url[1:]])
		log(item.link)

	# reddit
	if urlparse.urlparse(item.link).netloc == 'www.reddit.com':
		match = lxml.html.fromstring(item.desc).xpath('//a[text()="[link]"]/@href')
		if len(match):
			item.link = match[0]
			log(item.link)

	# check relative urls
	if urlparse.urlparse(item.link).netloc is '':
		item.link = urlparse.urljoin(feedurl, item.link)

	# check unwanted uppercase title
	if len(item.title) > 20 and item.title.isupper():
		item.title = item.title.title()

	# content already provided?
	count_content = countWord(item.content)
	count_desc = countWord(item.desc)

	log('desc: %s words, content: %s words' % (count_content, count_desc))

	if max(count_content, count_desc) > 500:
		log('long enough')
		return True

	if count_content > 5*count_desc > 0 and count_content > 50:
		log('content bigger enough')
		return True

	# check cache and previous errors
	if item.link in cache:
		content = cache.get(item.link)
		match = re.search(r'^error-([a-z]{2,10})$', content)
		if match:
			if cache.isYoungerThan(DELAY*60):
				log('cached error: %s' % match.groups()[0])
				return True
			else:
				log('old error')
		else:
			log('cached')
			setContent(item, cache.get(item.link))
			return True

	# super-fast mode
	if fast:
		log('skipped')
		return False

	# download
	try:
		url = item.link.encode('utf-8')
		con = urllib2.build_opener(HTMLDownloader()).open(url, timeout=TIMEOUT)
		data = con.read()
	except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as error:
		log('http error')
		cache.set(item.link, 'error-http')
		return True

	out = readability.Document(data, url=con.url).summary(True)

	if countWord(out) > max(count_content, count_desc) > 0:
		setContent(item, out)
		cache.set(item.link, out)
	else:
		log('not bigger enough')
		cache.set(item.link, 'error-length')
		return True

	return True

def Gather(url, cachePath, mode='feed'):
	cache = Cache(cachePath, url)

	# fetch feed
	if cache.isYoungerThan(DELAY*60) and url in cache:
		log('xml cached')
		xml = cache.get(url)
	else:
		try:
			req = urllib2.Request(url)
			req.add_unredirected_header('User-Agent', UA_RSS)
			xml = urllib2.urlopen(req).read()
			cache.set(url, xml)
		except (urllib2.HTTPError, urllib2.URLError):
			return False

	rss = feeds.parse(xml)
	size = len(rss)

	# set
	startTime = time.time()
	for i, item in enumerate(rss.items):
		if mode == 'progress':
			if MAX_ITEM == 0:
				print '%s/%s' % (i+1, size)
			else:
				print '%s/%s' % (i+1, min(MAX_ITEM, size))
			sys.stdout.flush()

		if i+1 > LIM_ITEM > 0:
			item.remove()
		elif time.time() - startTime > MAX_TIME >= 0 or i+1 > MAX_ITEM > 0:
			if Fill(item, cache, url, True) is False:
				item.remove()
		else:
			Fill(item, cache, url)

	log(len(rss))

	return rss.tostring(xml_declaration=True, encoding='UTF-8')

if __name__ == '__main__':
	url, options = parseOptions(OPTIONS)

	if 'REQUEST_URI' in os.environ:
		print 'Status: 200'

		if options == 'progress':
			print 'Content-Type: application/octet-stream'
		else:
			print 'Content-Type: text/xml'
		print

		cache = os.getcwd() + '/cache'
		log(url)
	else:
		cache =	os.path.expanduser('~') + '/.cache/morss'

	if url is None:
		print 'Please provide url.'
		sys.exit(1)

	if options == 'progress':
		MAX_TIME = -1
	if options == 'cache':
		MAX_TIME = 0

	RSS = Gather(url, cache, options)

	if RSS is not False and options != 'progress':
		if 'REQUEST_URI' in os.environ or not os.getenv('DEBUG', False):
			print RSS

	if RSS is False and options != 'progress':
		print 'Error fetching feed.'

	log('done')
