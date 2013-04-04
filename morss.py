#!/usr/bin/env python
import sys
import os
from os.path import expanduser
from lxml import etree
import string
import urllib2
from cookielib import CookieJar
import chardet

SERVER = True

if SERVER:
	import httplib
	httplib.HTTPConnection.debuglevel = 1

	import cgitb
	cgitb.enable()

def log(txt):
	if not SERVER and os.getenv('DEBUG', False):
		print txt
	if SERVER:
		with open('morss.log', 'a') as file:
			if isinstance(txt, str):
				file.write(txt.encode('utf-8') + "\n")

class Info:
	def __init__(self, item, feed):
		self.item = item
		self.feed = feed

		self.data = False
		self.page = False
		self.html = False
		self.con = False
		self.opener = False
		self.enc = False

		self.link = self.item.findtext('link')
		self.desc = self.item.xpath('description')[0]

	def fetch(self):
		log(self.link)
		if not self.findCache():
			self.download()
			self.chardet()
			self.fetchDesc()
		self.save()
		log(self.enc)

	def parseHTML(self):
		if self.enc is False:
			self.page = etree.HTML(self.data)
		else:
			try:
				self.page = etree.HTML(self.data.decode(self.enc, 'ignore'))
			except ValueError:
				self.page = etree.HTML(self.data)


	def save(self):
		self.feed.save()

	def findCache(self):
		if self.feed.cache is not False:
			xpath = "//link[text()='" + self.link + "']/../description/text()"
			match = self.feed.cache.xpath(xpath)
			if len(match):
				log('cached')
				self.desc.text = match[0]
				return True
		return False

	def fetchDesc(self):
		self.parseHTML()
		match =	self.page.xpath(self.feed.rule)
		if len(match):
			self.html = match[0]
			self.deleteTags()
			self.desc.text = etree.tostring(self.html).decode(self.enc, 'ignore')
			log('ok txt')
		else:
			log('no match')

	def download(self):
		try:
			cj = CookieJar()
			self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
			self.con = self.opener.open(self.link.encode('utf-8'))
			self.data = self.con.read()
		except (urllib2.HTTPError, urllib2.URLError) as error:
			log(error)
			log('http error')

	def chardet(self):
		if self.con.headers.getparam('charset'):
			log('header')
			self.enc = self.con.headers.getparam('charset')
			return

		page = etree.HTML(self.data)
		header = page.xpath("//head/meta[@http-equiv='Content-Type']/@content")
		if len(header) and len(header[0].split("=")):
			log('meta')
			self.enc = header[0].split("=")[1]
			return

		header = page.xpath("//head/meta[@charset]/@charset")
		if len(header):
			log('meta2')
			self.enc = header[0]
			return

		log('chardet')
		self.enc = chardet.detect(self.data)['encoding']

	def deleteTags(self):
		for tag in self.feed.trash:
			for elem in self.html.xpath(tag):
				elem.getparent().remove(elem)

class Feed:
	def __init__(self, impl, data, cachePath):
		self.rulePath = 'rules'
		self.rule = '//article|//h1/..'

		self.trash = ['//script', '//iframe', '//object', '//noscript', '//form', '//h1']
		self.max = 70

		self.cachePath = cachePath
		self.cacheFile = False
		self.cache = False
		self.impl = impl

		self.items = []
		self.rss = False
		self.out = False

		if self.impl == 'server':
			self.url = data
			self.xml = False
		else:
			self.url = False
			self.xml = data

	def save(self):
		self.out = etree.tostring(self.rss, xml_declaration=True, pretty_print=True)
		open(self.cacheFile, 'w').write(self.out)

	def getData(self):
		if self.impl == 'server':
			req = urllib2.Request(self.url)
			req.add_unredirected_header('User-Agent', '')
			self.xml = urllib2.urlopen(req).read()
		self.cleanXml()

	def setCache(self):
		if self.cache is not False:
			return

		self.parse()
		key = str(hash(self.rss.xpath('//channel/title/text()')[0]))
		self.cacheFile = self.cachePath + "/" + key
		log(self.cacheFile)
		if not os.path.exists(self.cachePath):
			os.makedirs(self.cachePath)

		if os.path.exists(self.cacheFile):
			self.cache = etree.XML(open(self.cacheFile, 'r').read())

	def parse(self):
		if self.rss is not False:
			return

		self.rss = etree.XML(self.xml)

	def setItems(self):
		self.items = [Info(e, self) for e in self.rss.xpath('//item')]
		if self.max:
			self.items = self.items[:self.max]

	def fill(self):
		self.parseRules()
		log(self.rule)
		for item in self.items:
			item.fetch()

	def cleanXml(self):
		table = string.maketrans('', '')
		self.xml = self.xml.translate(table, table[:32]).lstrip()

	def parseRules(self):
		if self.impl == 'server':
			rules = open(self.rulePath, "r").read().split("\n\n")
			rules = [r.split('\n') for r in rules]
			for rule in rules:
				if rule[1] == self.url:
					self.rule = rule[2]
					return
		else:
			if len(sys.argv) > 1:
				self.rule = sys.argv[1]

if __name__ == "__main__":
	if SERVER:
		print 'Content-Type: text/html\n'
		url = os.environ['REQUEST_URI'][len(os.environ['SCRIPT_NAME'])+1:]
		url = 'http://' + url.replace(' ', '%20')
		log(url)
		RSS = Feed('server', url, os.getcwd() + '/cache')
	else:
		xml =	sys.stdin.read()
		cache =	expanduser('~') + '/.cache/morss'
		RSS = Feed('liferea', xml, os.getcwd() + '/cache')

	RSS.getData()
	RSS.parse()
	RSS.setCache()
	RSS.setItems()
	RSS.fill()
	RSS.save()

	if SERVER or not os.getenv('DEBUG', False):
		print RSS.out
	else:
		print 'done'
