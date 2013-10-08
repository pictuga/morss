#!/usr/bin/env python

from ConfigParser import ConfigParser
from fnmatch import fnmatch
import feeds
import re

import urllib2
import lxml.html
import urlparse

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

def getString(html, expr):
	matches = html.xpath(toclass(expr))
	if len(matches):
		out = ''
		for match in matches:
			if isinstance(match, basestring):
				out += match
			elif isinstance(match, lxml.html.HtmlElement):
				out += lxml.html.tostring(match)
		return out
	else:
		return ''

def build(link, data=None):
	rule = getRule(link)
	if rule is False:
		return False

	if data is None:
		data = urllib2.urlopen(link).read()

	html = lxml.html.fromstring(data)
	feed = feeds.FeedParserAtom()

	if 'title' in rule:
		feed.title = getString(html, rule['title'])

	if 'items' in rule:
		for item in html.xpath(toclass(rule['items'])):
			feedItem = {}

			if 'item_title' in rule:
				feedItem['title'] = getString(item, rule['item_title'])
			if 'item_link' in rule:
				url = getString(item, rule['item_link'])
				url = urlparse.urljoin(link, url)
				feedItem['link'] = url
			if 'item_desc' in rule:
				feedItem['desc'] = getString(item, rule['item_desc'])
			if 'item_content' in rule:
				feedItem['content'] = getString(item, rule['item_content'])
			if 'item_time' in rule:
				feedItem['updated'] = getString(item, rule['item_time'])

			feed.items.append(feedItem)
	return feed
