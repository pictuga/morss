#!/usr/bin/env python
import sys
import os
import os.path
import time

from fnmatch import fnmatch
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
HOLD = False

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
		if HOLD:
			open('morss.log', 'a').write("%s\n" % repr(txt))
		else:
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

class ParseOptions:
	def __init__(self):
		self.url = ''
		self.options = {}
		roptions = []

		if 'REQUEST_URI' in os.environ:
			self.url = os.environ['REQUEST_URI'][1:]

			if 'REDIRECT_URL' not in os.environ:
				self.url = self.url[len(os.environ['SCRIPT_NAME']):]

			if self.url.startswith(':'):
				roptions = self.url.split('/')[0].split(':')[1:]
				self.url = self.url.split('/', 1)[1]
		else:
			if len(sys.argv) <= 1:
				return (None, [])

			roptions = sys.argv[1:-1]
			self.url = sys.argv[-1]

		if urlparse.urlparse(self.url).scheme not in PROTOCOL:
			self.url = 'http://' + self.url

		for option in roptions:
			split = option.split('=', 1)
			if len(split) > 1:
				if split[0].lower() == 'true':
					self.options[split[0]] = True
				if split[0].lower() == 'false':
					self.options[split[0]] = False

				self.options[split[0]] = split[1]
			else:
				self.options[split[0]] = True

	def __getattr__(self, key):
		if key in self.options:
			return self.options[key]
		else:
			return False

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
		self._cache[key] = b64encode(str(content) or '')

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

	def new(self, key):
		""" Returns a Cache object in the same directory """
		if key != self._key:
			return Cache(self._dir, key)
		else:
			return self

class SimpleDownload(urllib2.HTTPCookieProcessor):
	"""
	Custom urllib2 handler to download a page, using etag/last-modified headers,
	to save bandwidth. The given headers are added back into the header on error
	304 for easier use.
	"""
	def __init__(self, cache="", etag=None, lastmodified=None, useragent=UA_HTML, decode=False, cookiejar=None):
		urllib2.HTTPCookieProcessor.__init__(self, cookiejar)
		self.cache = cache
		self.etag = etag
		self.lastmodified = lastmodified
		self.useragent = useragent
		self.decode = decode

	def http_request(self, req):
		urllib2.HTTPCookieProcessor.http_request(self, req)
		req.add_unredirected_header('Accept-Encoding', 'gzip')
		req.add_unredirected_header('User-Agent', self.useragent)
		req.add_unredirected_header('Referer', 'http://%s' % req.get_host())
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
			if self.decode:
				data = decodeHTML(data, resp)

			fp = StringIO(data)
			old_resp = resp
			resp = urllib2.addinfourl(fp, old_resp.headers, old_resp.url, old_resp.code)
			resp.msg = old_resp.msg
		return resp

	https_response = http_response
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

def Fix(item, feedurl='/'):
	""" Improves feed items (absolute links, resolve feedburner links, etc) """

	# check unwanted uppercase title
	if len(item.title) > 20 and item.title.isupper():
		item.title = item.title.title()

	# check if it includes link
	if not item.link:
		log('no link')
		return item

	# check relative urls
	item.link = urlparse.urljoin(feedurl, item.link)

	# google
	if fnmatch(item.link, 'http://www.google.com/url?q=*'):
		item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['q'][0]
		log(item.link)

	# facebook
	if fnmatch(item.link, 'https://www.facebook.com/l.php?u=*'):
		item.link = urlparse.parse_qs(urlparse.urlparse(item.link).query)['u'][0]
		log(item.link)

	# feedburner
	feeds.NSMAP['feedburner'] = 'http://rssnamespace.org/feedburner/ext/1.0'
	if item.id:
		item.link = item.id
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

	return item

def Fill(item, cache, feedurl='/', fast=False):
	""" Returns True when it has done its best """

	if not item.link:
		log('no link')
		return item

	log(item.link)

	# content already provided?
	count_content = countWord(item.content)
	count_desc = countWord(item.desc)

	if max(count_content, count_desc) > 500:
		if count_desc > count_content:
			item.content = item.desc
			del item.desc
			log('reversed sizes')
		log('long enough')
		return True

	if count_content > 5*count_desc > 0 and count_content > 50:
		log('content bigger enough')
		return True

	link = item.link

	# twitter
	if urlparse.urlparse(feedurl).netloc == 'twitter.com':
		match = lxml.html.fromstring(item.content).xpath('//a/@data-expanded-url')
		if len(match):
			link = match[0]
			log(link)
		else:
			link = None

	# facebook, do nothing for now FIXME
	if urlparse.urlparse(feedurl).netloc == 'graph.facebook.com':
		link = None

	if link is None:
		log('no used link')
		return True

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
			item.pushContent(cache.get(link))
			return True

	# super-fast mode
	if fast:
		log('skipped')
		return False

	# download
	try:
		url = link.encode('utf-8')
		con = urllib2.build_opener(SimpleDownload(decode=True)).open(url, timeout=TIMEOUT)
		data = con.read()
	except (urllib2.URLError, httplib.HTTPException, socket.timeout):
		log('http error')
		cache.set(link, 'error-http')
		return True

	if con.info().type not in MIMETYPE['html'] and con.info().type != 'text/plain':
		log('non-text page')
		cache.set(link, 'error-type')
		return True

	out = readability.Document(data, url=con.url).summary(True)

	if countWord(out) > max(count_content, count_desc) > 0:
		item.pushContent(out)
		cache.set(link, out)
	else:
		log('not bigger enough')
		cache.set(link, 'error-length')
		return True

	return True

def Gather(url, cachePath, options):
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
			opener = SimpleDownload(cache.get(url), cache.get('etag'), cache.get('lastmodified'), decode=False)
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
		feed = feedify.Builder(url, xml)
		feed.build()
		rss = feed.feed
	elif style == 'html':
		match = lxml.html.fromstring(xml).xpath("//link[@rel='alternate'][@type='application/rss+xml' or @type='application/atom+xml']/@href")
		if len(match):
			link = urlparse.urljoin(url, match[0])
			return Gather(link, cachePath, options)
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
		item = Fix(item, url)
		if options.progress:
			if MAX_ITEM == 0:
				print '%s/%s' % (i+1, size)
			else:
				print '%s/%s' % (i+1, min(MAX_ITEM, size))
			sys.stdout.flush()

		if i+1 > LIM_ITEM > 0:
			item.remove()
			continue
		elif time.time() - startTime > MAX_TIME >= 0 or i+1 > MAX_ITEM > 0:
			if Fill(item, cache, url, True) is False:
				item.remove()
				continue
		else:
			Fill(item, cache, url)

		if item.desc and item.content:
			if options.clip:
				item.content = item.desc + "<br/><br/><center>* * *</center><br/><br/>" + item.content
				del item.desc
			if not options.keep:
				del item.desc

	log(len(rss.items))
	log(time.time() - startTime)

	return rss.tostring(xml_declaration=True, encoding='UTF-8')

if __name__ == '__main__':
	options = ParseOptions()
	url = options.url

	DEBUG = bool(options.debug)

	if 'REQUEST_URI' in os.environ:
		HOLD = True

		if 'HTTP_IF_NONE_MATCH' in os.environ and not options.force:
			if time.time() - int(os.environ['HTTP_IF_NONE_MATCH'][1:-1]) < DELAY:
				print 'Status: 304'
				print
				log(url)
				log('etag good')
				sys.exit(0)

		print 'Status: 200'
		print 'ETag: "%s"' % int(time.time())

		if options.html:
			print 'Content-Type: text/html'
		elif options.debug:
			print 'Content-Type: text/plain'
		elif options.progress:
			print 'Content-Type: application/octet-stream'
		else:
			print 'Content-Type: text/xml'
		print ''

		HOLD = False

		cache = os.getcwd() + '/cache'
	else:
		cache =	os.path.expanduser('~') + '/.cache/morss'

	if url is None:
		print 'Please provide url.'
		sys.exit(1)

	if options.progress:
		MAX_TIME = -1
	if options.cache:
		MAX_TIME = 0

	RSS = Gather(url, cache, options)

	if RSS is not False and not options.progress and not DEBUG:
			print RSS

	if RSS is False and 'progress' not in options:
		print 'Error fetching feed.'

	log('done')
