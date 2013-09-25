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

def getRule(link=URL):
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

def getString(expr, html):
	match = html.xpath(toclass(expr))
	if len(match):
		return match[0].text_content()
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
		feed.title = html.xpath(toclass(rule['title']))[0]

	if 'items' in rule:
		for item in html.xpath(toclass(rule['items'])):
			feedItem = {}

			if 'item_title' in rule:
				feedItem['title'] = item.xpath(toclass(rule['item_title']))[0]
			if 'item_link' in rule:
				url = item.xpath(toclass(rule['item_link']))[0]
				url = urlparse.urljoin(link, url)
				feedItem['link'] = url
			if 'item_desc' in rule:
				feedItem['desc'] = lxml.html.tostring(item.xpath(toclass(rule['item_desc']))[0], encoding='unicode')
			if 'item_content' in rule:
				feedItem['content'] = lxml.html.tostring(item.xpath(toclass(rule['item_content']))[0])

			feed.items.append(feedItem)
	return feed
