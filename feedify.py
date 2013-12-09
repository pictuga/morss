#!/usr/bin/env python

from ConfigParser import ConfigParser
from fnmatch import fnmatch
import feeds
import morss
import re

import urllib2
import lxml.html
import json
import urlparse

import time

def toclass(query):
	pattern = r'\[class=([^\]]+)\]'
	repl = r'[@class and contains(concat(" ", normalize-space(@class), " "), " \1 ")]'
	return re.sub(pattern, repl, query)

def getRule(link):
	config = ConfigParser()
	config.read('feedify.ini')

	for section in config.sections():
		values = dict(config.items(section))
		values['path'] = values['path'].split('\n')[1:]
		for path in values['path']:
			if fnmatch(link, path):
				return values
	return False

def supported(link):
	return getRule(link) is not False

def formatString(string, getter, error=False):
	out = ""
	char = string[0]

	follow = string[1:]

	if char == '"':
		match = follow.partition('"')
		out = match[0]
		if len(match) >= 2:
			next = match[2]
		else:
			next = None
	elif char == '{':
		match = follow.partition('}')
		try:
			test = formatString(match[0], getter, True)
		except ValueError, KeyError:
			pass
		else:
			out = test

		next = match[2]
	elif char == ' ':
		next = follow
	elif re.search(r'^([^{}<>" ]+)(?:<"([^>]+)">)?(.*)$', string):
		match = re.search(r'^([^{}<>" ]+)(?:<"([^>]+)">)?(.*)$', string).groups()
		rawValue = getter(match[0])
		if not isinstance(rawValue, basestring):
			if match[1] is not None:
				out = match[1].join(rawValue)
			else:
				out = ''.join(rawValue)
		if not out and error:
			raise ValueError
		next = match[2]
	else:
		raise ValueError('bogus string')

	if next is not None and len(next):
		return out + formatString(next, getter, error)
	else:
		return out

def PreWorker(url, cache):
	if urlparse.urlparse(url).netloc == 'graph.facebook.com':
		facebook = cache.new('facebook', True)
		token = urlparse.parse_qs(urlparse.urlparse(url).query)['access_token'][0]

		if 't'+token not in facebook:
			# this token ain't known, look for info about it
			eurl = "https://graph.facebook.com/debug_token?input_token={token}&access_token={app_token}".format(token=token, app_token=morss.FBAPPTOKEN)
			data = json.loads(urllib2.urlopen(eurl).read())['data']

			app_id = str(data['app_id'])
			user_id = str(data['user_id'])
			expires = int(data['expires_at'])
			short = 'issued_at' not in data

			facebook.set('t'+token, user_id)
			facebook.set('e'+token, expires)

			good = True

			# do some woodoo to know if we already have sth better

			if 'u'+user_id not in facebook:
				# grab a new one anyway, new user
				facebook.set('o'+user_id, token)
				good = True
			else:
				# maybe it's a better one
				last = facebook.get('u'+user_id)
				last_expires = facebook.get('e'+last)

				if expires > last_expires:
					# new is better
					good = True

			if good and short and app_id == morss.FBAPPID:
				eurl = "https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id={app_id}&client_secret={app_secret}&fb_exchange_token={short_lived_token}".format(app_id=morss.FBAPPID, app_secret=morss.FBSECRET, short_lived_token=token)
				values = urlparse.parse_qs(urllib2.urlopen(eurl).read().strip())

				token = values['access_token'][0]
				expires = int(time.time() + int(values['expires'][0]))

				facebook.set('t'+token, user_id)
				facebook.set('e'+token, expires)

			if good:
				facebook.set('u'+user_id, token)

		# hey look for a newer token and use it
		token = urlparse.parse_qs(urlparse.urlparse(url).query)['access_token'][0]
		user_id = facebook.get('t'+token)
		last = facebook.get('u'+user_id)
		original = facebook.get('o'+user_id)

		nurl = url.replace(token, last)
		ncache = url.replace(token, original)
		cache.set('redirect', nurl)
		cache.set('cache', ncache)

class Builder(object):
	def __init__(self, link, data=None, cache=False):
		self.link = link
		self.cache = cache

		if data is None:
			data = urllib2.urlopen(link).read()
		self.data = data

		self.rule = getRule(link)

		if self.rule['mode'] == 'xpath':
			if not isinstance(self.data, unicode):
				self.data = self.data.decode(morss.detEncoding(self.data), 'replace')
			self.doc = lxml.html.fromstring(self.data)
		elif self.rule['mode'] == 'json':
			self.doc = json.loads(data)

		self.feed = feeds.FeedParserAtom()

	def raw(self, html, expr):
		if self.rule['mode'] == 'xpath':
			return html.xpath(toclass(expr))

		elif self.rule['mode'] == 'json':
			a = [html]
			b = []
			for x in expr.strip(".").split("."):
				match = re.search(r'^([^\[]+)(?:\[([0-9]+)\])?$', x).groups()
				for elem in a:
					if isinstance(elem, dict):
						kids = elem.get(match[0])
						if kids is None:
							pass
						elif isinstance(kids, list):
							[b.append(i) for i in kids]
						elif isinstance(kids, basestring):
							b.append(kids.replace('\n', '<br/>'))
						else:
							b.append(kids)

				if match[1] is None:
					a = b
				else:
					if len(b)-1 >= int(match[1]):
						a = [b[int(match[1])]]
					else:
						a = []
				b = []
			return a

	def strings(self, html, expr):
		if self.rule['mode'] == 'xpath':
			out = []
			for match in self.raw(html, expr):
				if isinstance(match, basestring):
					out.append(match)
				elif isinstance(match, lxml.html.HtmlElement):
					out.append(lxml.html.tostring(match))
			return out

		elif self.rule['mode'] == 'json':
			return self.raw(html, expr)

	def string(self, html, expr):
		getter = lambda x: self.strings(html, x)
		return formatString(self.rule[expr], getter)

	def build(self):
		if 'title' in self.rule:
			self.feed.title = self.string(self.doc, 'title')

		if 'items' in self.rule:
			matches = self.raw(self.doc, self.rule['items'])
			if matches and len(matches):
				for item in matches:
					feedItem = {}

					if 'item_title' in self.rule:
						feedItem['title'] = self.string(item, 'item_title')
					if 'item_link' in self.rule:
						url = self.string(item, 'item_link')
						url = urlparse.urljoin(self.link, url)
						feedItem['link'] = url
					if 'item_desc' in self.rule:
						feedItem['desc'] = self.string(item, 'item_desc')
					if 'item_content' in self.rule:
						feedItem['content'] = self.string(item, 'item_content')
					if 'item_time' in self.rule:
						feedItem['updated'] = self.string(item, 'item_time')

					self.feed.items.append(feedItem)


		if urlparse.urlparse(self.link).netloc == 'graph.facebook.com':
			if self.cache:
				facebook = self.cache.new('facebook', True)
				token = urlparse.parse_qs(urlparse.urlparse(self.link).query)['access_token'][0]
				expires = facebook.get('e'+token)
				lifespan = expires - time.time()

				if lifespan < 5*24*3600:
					new = self.feed.items.append()
					new.title = "APP AUTHORISATION RENEWAL NEEDED"
					new.link = "https://www.facebook.com/dialog/oauth?client_id={app_id}&redirect_uri=http://test.morss.it/:facebook/".format(app_id=morss.FBAPPID)
					new.desc = "Please renew your Facebook app token for this app to keep working for this feed.<br/><a href='{}'>Go!</a>".format(new.link)
					new.time = expires
