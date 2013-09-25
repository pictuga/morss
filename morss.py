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
import feedify

import httplib
import urllib2
import socket
import chardet
import urlparse

from gzip import GzipFile
from StringIO import StringIO

from readability import readability

LIM_ITEM = 100	# deletes what's beyond
MAX_ITEM = 50	# cache-only beyond
MAX_TIME = 7	# cache-only after (in sec)
DELAY = 10*60	# xml cache & ETag cache (in sec)
TIMEOUT = 2	# http timeout (in sec)

DEBUG = False

UA_RSS = 'Liferea/1.8.12 (Linux; fr_FR.utf8; http://liferea.sf.net/)'
UA_HTML = 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.6; en-US; rv:1.9.2.11) Gecko/20101012 Firefox/3.6.11'

MIMETYPE = {	'xml':	['text/xml', 'application/xml', 'application/rss+xml', 'application/rdf+xml', 'application/atom+xml'],
				'html':	['text/html', 'application/xhtml+xml']}

PROTOCOL = ['http', 'https', 'ftp']

if 'REQUEST_URI' in os.environ:
	httplib.HTTPConnection.debuglevel = 1

	import cgitb
	cgitb.enable()

def log(txt):
	if DEBUG:
		print repr(txt)


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

def parseOptions():
	url = ''
	options = []

	if 'REQUEST_URI' in os.environ:
		url = os.environ['REQUEST_URI'][1:]

		if 'REDIRECT_URL' not in os.environ:
			url = url[len(os.environ['SCRIPT_NAME']):]

		if url.startswith(':'):
			options = url.split('/')[0].split(':')[1:]
			url = url.split('/', 1)[1]

		if urlparse.urlparse(url).scheme not in PROTOCOL:
			url = 'http://' + url
	else:
		if len(sys.argv) <= 1:
			return (None, [])

		options = sys.argv[1:-1]
		url = sys.argv[-1]

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
		self._cache[key] = b64encode(content or '')

	def save(self):
		if len(self._cache) == 0:
			return

		out = []
		for (key, bdata) in self._cache.iteritems():
			out.append(str(key) + "\t" + bdata)
		out.append("_key\t" + self._key)
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
	def __init__(self, useragent=UA_HTML, cookiejar=None):
		urllib2.HTTPCookieProcessor.__init__(self, cookiejar)
		self.useragent = useragent

	def http_request(self, req):
		urllib2.HTTPCookieProcessor.http_request(self, req)
		req.add_unredirected_header('Accept-Encoding', 'gzip')
		req.add_unredirected_header('User-Agent', self.useragent)
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
			if resp.info().type in MIMETYPE['html']:
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
			data = decodeHTML(data, resp)

			fp = StringIO(data)
			old_resp = resp
			resp = urllib2.addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
			resp.msg = old_resp.msg
		return resp

	https_response = http_response
	https_request = http_request

class CacheDownload(urllib2.BaseHandler):
	"""
	Custom urllib2 handler to download a page, using etag/last-modified headers,
	to save bandwidth. The given headers are added back into the header on error
	304 for easier use.
	"""
	def __init__(self, cache="", etag=None, lastmodified=None, useragent=UA_RSS):
		self.cache = cache
		self.etag = etag
		self.lastmodified = lastmodified
		self.useragent = useragent

	def http_request(self, req):
		req.add_unredirected_header('User-Agent', self.useragent)
		if self.cache:
			if self.etag:
				req.add_unredirected_header('If-None-Match', self.etag)
			if self.lastmodified:
				req.add_unredirected_header('If-Modified-Since', self.lastmodified)
		return req

	def http_error_304(self, req, fp, code, msg, headers):
		log('http cached')
		if self.etag:
			headers.addheader('etag', self.etag)
		if self.lastmodified:
			headers.addheader('last-modified', self.lastmodified)
		resp = urllib2.addinfourl(StringIO(self.cache), headers, req.get_full_url(), 200)
		return resp

	https_request = http_request

def decodeHTML(data, con=None):
	if con is not None and con.headers.getparam('charset'):
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

def Fill(item, cache, feedurl='/', fast=False, clip=False):
	""" Returns True when it has done its best """

	if not item.link:
		log('no link')
		return True

	log(item.link)

	# check relative urls
	item.link = urlparse.urljoin(feedurl, item.link)

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
		t = {'A':'0', 'B':'.', 'C':'/', 'D':'?', 'E':'-', 'H':',', 'I':'_', 'L':'http://', 'S':'www.', 'N':'.com', 'O':'.co.uk'}
		item.link = ''.join([(t[s[0]] if s[0] in t else '=') + s[1:] for s in url[1:]])
		log(item.link)

	# reddit
	if urlparse.urlparse(item.link).netloc == 'www.reddit.com':
		match = lxml.html.fromstring(item.desc).xpath('//a[text()="[link]"]/@href')
		if len(match):
			item.link = match[0]
			log(item.link)

	# check unwanted uppercase title
	if len(item.title) > 20 and item.title.isupper():
		item.title = item.title.title()

	# content already provided?
	count_content = countWord(item.content)
	count_desc = countWord(item.desc)

	if max(count_content, count_desc) > 500:
		log('long enough')
		return True

	if count_content > 5*count_desc > 0 and count_content > 50:
		log('content bigger enough')
		return True

	link = item.link

	# twitter
	if urlparse.urlparse(item.link).netloc == 'twitter.com':
		match = lxml.html.fromstring(item.content).xpath('//a/@data-expanded-url')
		if len(match):
			link = match[0]
			clip = True
			log(link)

	# check cache and previous errors
	if link in cache:
		content = cache.get(link)
		match = re.search(r'^error-([a-z]{2,10})$', content)
		if match:
			if cache.isYoungerThan(DELAY):
				log('cached error: %s' % match.groups()[0])
				return True
			else:
				log('old error')
		else:
			log('cached')
			item.pushContent(cache.get(link), clip)
			return True

	# super-fast mode
	if fast:
		log('skipped')
		return False

	# download
	try:
		url = link.encode('utf-8')
		con = urllib2.build_opener(HTMLDownloader()).open(url, timeout=TIMEOUT)
		data = con.read()
	except (urllib2.URLError, httplib.HTTPException, socket.timeout):
		log('http error')
		cache.set(link, 'error-http')
		return True

	if con.info().maintype != 'text':
		log('non-text page')
		cache.set(link, 'error-type')
		return True

	out = readability.Document(data, url=con.url).summary(True)

	if countWord(out) > max(count_content, count_desc) > 0:
		item.pushContent(out, clip)
		cache.set(link, out)
	else:
		log('not bigger enough')
		cache.set(link, 'error-length')
		return True

	return True

def Gather(url, cachePath, progress=False):
	log(url)

	url = url.replace(' ', '%20')
	cache = Cache(cachePath, url)

	log(cache._hash)

	# fetch feed
	if cache.isYoungerThan(DELAY) and 'xml' in cache and 'style' in cache:
		log('xml cached')
		xml = cache.get('xml')
		style = cache.get('style')
	else:
		try:
			opener = CacheDownload(cache.get(url), cache.get('etag'), cache.get('lastmodified'))
			con = urllib2.build_opener(opener).open(url, timeout=TIMEOUT)
			xml = con.read()
		except (urllib2.URLError, httplib.HTTPException, socket.timeout):
			return False

		cache.set('xml', xml)
		cache.set('etag', con.headers.getheader('etag'))
		cache.set('lastmodified', con.headers.getheader('last-modified'))

		if xml[:5] == '<?xml' or con.info().type in MIMETYPE['xml']:
			style = 'normal'
		elif feedify.supported(url):
			style = 'feedify'
		elif con.info().type in MIMETYPE['html']:
			style = 'html'
		else:
			style = 'none'
			log(con.info().type)

		cache.set('style', style)

	log(style)

	if style == 'normal':
		rss = feeds.parse(xml)
	elif style == 'feedify':
		xml = decodeHTML(xml)
		rss = feedify.build(url, xml)
	elif style == 'html':
		match = lxml.html.fromstring(xml).xpath("//link[@rel='alternate'][@type='application/rss+xml' or @type='application/atom+xml']/@href")
		if len(match):
			link = urlparse.urljoin(url, match[0])
			return Gather(link, cachePath, progress)
		else:
			log('no-link html')
			return False
	else:
		log('random page')
		return False

	size = len(rss.items)

	# set
	startTime = time.time()
	for i, item in enumerate(rss.items):
		if progress:
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

	log(len(rss.items))
	log(time.time() - startTime)

	return rss.tostring(xml_declaration=True, encoding='UTF-8')

if __name__ == '__main__':
	url, options = parseOptions()
	DEBUG = 'debug' in options

	if 'REQUEST_URI' in os.environ:
		if 'HTTP_IF_NONE_MATCH' in os.environ and 'force' not in options:
			if time.time() - int(os.environ['HTTP_IF_NONE_MATCH'][1:-1]) < DELAY:
				print 'Status: 304'
				print
				log(url)
				log('etag good')
				sys.exit(0)

		print 'Status: 200'
		print 'ETag: "%s"' % int(time.time())

		if 'html' in options:
			print 'Content-Type: text/html'
		elif 'debug' in options:
			print 'Content-Type: text/plain'
		elif 'progress' in options:
			print 'Content-Type: application/octet-stream'
		else:
			print 'Content-Type: text/xml'
		print

		cache = os.getcwd() + '/cache'
	else:
		cache =	os.path.expanduser('~') + '/.cache/morss'

	if url is None:
		print 'Please provide url.'
		sys.exit(1)

	if 'progress' in options:
		MAX_TIME = -1
	if 'cache' in options:
		MAX_TIME = 0

	RSS = Gather(url, cache, 'progress' in options)

	if RSS is not False and 'progress' not in options and not DEBUG:
			print RSS

	if RSS is False and 'progress' not in options:
		print 'Error fetching feed.'

	log('done')
