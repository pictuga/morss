# This file is part of morss
#
# Copyright (C) 2013-2020 pictuga <contact@pictuga.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.

import csv
import json
import re
from copy import deepcopy
from datetime import datetime
from fnmatch import fnmatch

import dateutil.parser
import lxml.html
from dateutil import tz
from lxml import etree

from .readabilite import parse as html_parse
from .util import *

json.encoder.c_make_encoder = None

try:
    # python 2
    from ConfigParser import RawConfigParser
    from StringIO import StringIO
except ImportError:
    # python 3
    from configparser import RawConfigParser
    from io import StringIO

try:
    # python 2
    basestring
except NameError:
    # python 3
    basestring = unicode = str


def parse_rules(filename=None):
    if not filename:
        filename = pkg_path('feedify.ini')

    config = RawConfigParser()
    config.read(filename)

    rules = dict([(x, dict(config.items(x))) for x in config.sections()])

    for section in rules.keys():
        # for each ruleset

        for arg in rules[section].keys():
            # for each rule

            if rules[section][arg].startswith('file:'):
                file_raw = open(data_path(rules[section][arg][5:])).read()
                file_clean = re.sub('<[/?]?(xsl|xml)[^>]+?>', '', file_raw)
                rules[section][arg] = file_clean

            elif '\n' in rules[section][arg]:
                rules[section][arg] = rules[section][arg].split('\n')[1:]

    return rules


def parse(data, url=None, encoding=None, ruleset=None):
    " Determine which ruleset to use "

    if ruleset is not None:
        rulesets = [ruleset]

    else:
        rulesets = parse_rules().values()

    parsers = [FeedXML, FeedHTML, FeedJSON]

    # 1) Look for a ruleset based on path

    if url is not None:
        for ruleset in rulesets:
            if 'path' in ruleset:
                for path in ruleset['path']:
                    if fnmatch(url, path):
                        parser = [x for x in parsers if x.mode == ruleset.get('mode')][0] # FIXME what if no mode specified?
                        return parser(data, ruleset, encoding=encoding)

    # 2) Try each and every parser

    # 3) Look for working ruleset for given parser
        # 3a) See if parsing works
        # 3b) See if .items matches anything

    for parser in parsers:
        try:
            feed = parser(data, encoding=encoding)

        except (ValueError, SyntaxError):
            # parsing did not work
            pass

        else:
            # parsing worked, now we try the rulesets

            ruleset_candidates = [x for x in rulesets if x.get('mode') in (parser.mode, None) and 'path' not in x]
                # 'path' as they should have been caught beforehands
                # try anyway if no 'mode' specified

            for ruleset in ruleset_candidates:
                feed.rules = ruleset

                try:
                    feed.items[0]

                except (AttributeError, IndexError, TypeError):
                    # parsing and or item picking did not work out
                    pass

                else:
                    # it worked!
                    return feed

    raise TypeError('no way to handle this feed')


class ParserBase(object):
    def __init__(self, data=None, rules=None, parent=None, encoding=None):
        if rules is None:
            rules = parse_rules()[self.default_ruleset]

        self.rules = rules

        if data is None:
            data = rules['base']

        self.parent = parent
        self.encoding = encoding

        self.root = self.parse(data)

    def parse(self, raw):
        pass

    def remove(self):
        # delete oneslf
        pass

    def tostring(self, **k):
        # output in its input format
        # to output in sth fancy (json, csv, html), change class type with .convert first
        pass

    def torss(self, **k):
        return self.convert(FeedXML).tostring(**k)

    def tojson(self, **k):
        return self.convert(FeedJSON).tostring(**k)

    def tocsv(self, encoding='unicode'):
        out = StringIO()
        c = csv.writer(out, dialect=csv.excel)

        for item in self.items:
            c.writerow([getattr(item, x) for x in item.dic])

        out.seek(0)
        out = out.read()

        if encoding != 'unicode':
            out = out.encode(encoding)

        return out

    def tohtml(self, **k):
        return self.convert(FeedHTML).tostring(**k)

    def convert(self, TargetParser):
        if type(self) == TargetParser:
            return self

        target = TargetParser()

        for attr in target.dic:
            if attr == 'items':
                for item in self.items:
                    target.append(item)

            else:
                setattr(target, attr, getattr(self, attr))

        return target

    # RULE-BASED FUNCTIONS

    def rule_search(self, rule):
        # xpath, return the first one only
        try:
            return self.rule_search_all(rule)[0]

        except IndexError:
            return None

    def rule_search_all(self, rule):
        # xpath, return all raw matches (useful to find feed items)
        pass

    def rule_search_last(self, rule):
        # xpath, return only the first raw match
        try:
            return self.rule_search_all(rule)[-1]

        except IndexError:
            return None

    def rule_create(self, rule):
        # create node based on rule
        # (duplicate, copy existing (or template) or create from scratch, if possible)
        # --> might want to create node_duplicate helper fns
        pass

    def rule_remove(self, rule):
        # remove node from its parent. Returns nothing
        pass

    def rule_set(self, rule, value):
        # set the value. Returns nothing
        pass

    def rule_str(self, rule):
        # GETs inside (pure) text from it
        pass

    # PARSERS

    def time_prs(self, x):
        # parse
        try:
            return parse_time(x)
        except ValueError:
            return None

    def time_fmt(self, x):
        # format
        try:
            time = parse_time(x)
            return time.strftime(self.rules.get('timeformat', self.default_timeformat))
        except ValueError:
            pass

    default_timeformat = "%D"

    # HELPERS

    def get_raw(self, rule_name):
        # get the raw output, for self.get_raw('items')
        if rule_name not in self.rules:
            return []

        return self.rule_search_all(self.rules[rule_name])

    def get(self, rule_name):
        # simple function to get nice text from the rule name
        # for use in @property, ie. self.get('title')
        if rule_name not in self.rules:
            return None

        return self.rule_str(self.rules[rule_name]) or None

    def set(self, rule_name, value):
        # simple function to set nice text from the rule name. Returns nothing
        if rule_name not in self.rules:
            return

        if value is None:
            self.rmv(rule_name)
            return

        try:
            self.rule_set(self.rules[rule_name], value)

        except AttributeError:
            # does not exist, have to create it
            try:
                self.rule_create(self.rules[rule_name])

            except AttributeError:
                # no way to create it, give up
                pass

            else:
                self.rule_set(self.rules[rule_name], value)

    def rmv(self, rule_name):
        # easy deleter
        if rule_name not in self.rules:
            return

        self.rule_remove(self.rules[rule_name])


class ParserXML(ParserBase):
    default_ruleset = 'rss-channel'
    mode = 'xml'
    mimetype = ['text/xml', 'application/xml', 'application/rss+xml',
        'application/rdf+xml', 'application/atom+xml', 'application/xhtml+xml']

    NSMAP = {'atom': 'http://www.w3.org/2005/Atom',
        'atom03': 'http://purl.org/atom/ns#',
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'rssfake': 'http://purl.org/rss/1.0/'}

    def parse(self, raw):
        parser = etree.XMLParser(recover=True, remove_blank_text=True, remove_pis=True) # remove_blank_text needed for pretty_print
        return etree.fromstring(raw, parser)

    def remove(self):
        return self.root.getparent().remove(self.root)

    def tostring(self, encoding='unicode', **k):
        return etree.tostring(self.root, encoding=encoding, method='xml', **k)

    def _rule_parse(self, rule):
        test = re.search(r'^(.*)/@([a-z]+)$', rule) # to match //div/a/@href
        return test.groups() if test else (rule, None)

    def _resolve_ns(self, rule):
        # shortname to full name
        match = re.search(r'^([^:]+):([^:]+)$', rule) # to match fakerss:content
        if match:
            match = match.groups()
            if match[0] in self.NSMAP:
                return "{%s}%s" % (self.NSMAP[match[0]], match[1].lower())

        return rule

    @staticmethod
    def _inner_html(xml):
        return (xml.text or '') + ''.join([etree.tostring(child, encoding='unicode') for child in xml])

    @staticmethod
    def _clean_node(xml):
        if xml is not None:
            if len(xml):
                [xml.remove(child) for child in xml]

            xml.text = None

    def rule_search_all(self, rule):
        try:
            match = self.root.xpath(rule, namespaces=self.NSMAP)
            if isinstance(match, str):
                # some xpath rules return a single string instead of an array (e.g. concatenate() )
                return [match,]

            else:
                return match

        except etree.XPathEvalError:
            return []

    def rule_create(self, rule):
        # duplicate, copy from template or create from scratch
        rrule, key = self._rule_parse(rule)

        # try recreating based on the rule (for really basic rules, ie. plain RSS) `/feed/item`
        if re.search(r'^[a-zA-Z0-9/:]+$', rrule):
            chain = rrule.strip('/').split('/')
            current = self.root

            if rrule[0] == '/':
                # we skip the first chain-element, as we _start_ from the first/root one
                # i.e. for "/rss/channel/title" we only keep "/channel/title"
                chain = chain[1:]

            for (i, node) in enumerate(chain):
                test = current.find(self._resolve_ns(node))

                if test is not None and i < len(chain) - 1:
                    # yay, go on
                    current = test

                else:
                    # opps need to create
                    element = etree.Element(self._resolve_ns(node))
                    current.append(element)
                    current = element

            return current

        # try duplicating from existing (works well with fucked up structures)
        match = self.rule_search_last(rrule)
        if match:
            element = deepcopy(match)
            match.getparent().append(element)
            return element

        return None

    def rule_remove(self, rule):
        rrule, key = self._rule_parse(rule)

        match = self.rule_search(rrule)

        if match is None:
            return

        elif key is not None:
            if key in match.attrib:
                del match.attrib[key]

        else:
            match.getparent().remove(match)

    def rule_set(self, rule, value):
        rrule, key = self._rule_parse(rule)

        match = self.rule_search(rrule)

        html_rich = ('atom' in rule or self.rules.get('mode') == 'html') \
            and rule in [self.rules.get('item_desc'), self.rules.get('item_content')]

        if key is not None:
            match.attrib[key] = value

        else:
            if html_rich:
                self._clean_node(match)
                match.append(lxml.html.fragment_fromstring(value, create_parent='div'))

                if self.rules.get('mode') == 'html':
                    match.find('div').drop_tag() # not supported by lxml.etree

                else: # i.e. if atom
                    match.attrib['type'] = 'xhtml'

            else:
                if match is not None and len(match):
                    self._clean_node(match)
                    match.attrib['type'] = 'html'

                match.text = value

    def rule_str(self, rule):
        match = self.rule_search(rule)

        html_rich = ('atom' in rule or self.mode == 'html') \
            and rule in [self.rules.get('item_desc'), self.rules.get('item_content')]

        if isinstance(match, etree._Element):
            if html_rich:
                # atom stuff
                return self._inner_html(match)

            else:
                return etree.tostring(match, method='text', encoding='unicode').strip()

        else:
            return match # might be None is no match


class ParserHTML(ParserXML):
    default_ruleset = 'html'
    mode = 'html'
    mimetype = ['text/html', 'application/xhtml+xml']

    def parse(self, raw):
        return html_parse(raw, encoding=self.encoding)

    def tostring(self, encoding='unicode', **k):
        return lxml.html.tostring(self.root, encoding=encoding, method='html', **k)

    def rule_search_all(self, rule):
        try:
            # do proper "class" matching (too "heavy" to type as-it in rules)
            pattern = r'\[class=([^\]]+)\]'
            repl = r'[@class and contains(concat(" ", normalize-space(@class), " "), " \1 ")]'
            rule = re.sub(pattern, repl, rule)

            match = self.root.xpath(rule)

            if isinstance(match, str):
                # for some xpath rules, see XML parser
                return [match,]

            else:
                return match

        except etree.XPathEvalError:
            return []

    def rule_create(self, rule):
        # try duplicating from existing (works well with fucked up structures)
        rrule, key = self._rule_parse(rule)

        match = self.rule_search_last(rule)
        if match is not None:
            element = deepcopy(match)
            match.getparent().append(element)

        else:
            raise AttributeError('no way to create item')


def parse_time(value):
    # parsing per se
    if value is None or value == 0:
        time = None

    elif isinstance(value, basestring):
        if re.match(r'^[0-9]+$', value):
            time = datetime.fromtimestamp(int(value))

        else:
            time = dateutil.parser.parse(value)

    elif isinstance(value, int):
        time = datetime.fromtimestamp(value)

    elif isinstance(value, datetime):
        time = value

    else:
        time = None

    # add default time zone if none set
    if time is not None and time.tzinfo is None:
            time = time.replace(tzinfo=tz.tzutc())

    return time


class ParserJSON(ParserBase):
    default_ruleset = 'json'
    mode = 'json'
    mimetype = ['application/json', 'application/javascript', 'text/javascript']

    def parse(self, raw):
        return json.loads(raw)

    def remove(self):
        # impossible to "delete" oneself per se but can clear all its items
        for attr in self.root:
            del self.root[attr]

    def tostring(self, encoding='unicode', **k):
        dump = json.dumps(self.root, ensure_ascii=False, **k) # ensure_ascii = False to have proper (unicode) string and not \u00

        if encoding != 'unicode':
            return dump.encode(encoding)

        else:
            return dump

    def _rule_parse(self, rule):
        return rule.split(".")

    def rule_search_all(self, rule):
        try:
            rrule = self._rule_parse(rule)
            cur = self.root

            for node in rrule:
                if node == '[]':
                    break
                else:
                    cur = cur[node]

            return cur if isinstance(cur, list) else [cur,]

        except (AttributeError, KeyError):
            return []

    def rule_create(self, rule):
        # create from scracth
        rrule = self._rule_parse(rule)
        cur = self.root

        for (i, node) in enumerate(rrule):
            if rrule[i+1] == '[]':
                if node in cur and isinstance(cur[node], list):
                    cur[node].append({})

                else:
                    cur[node] = [{}]

                return

            else:
                if node in cur:
                    # yay, go on
                    cur = cur[node]
                else:
                    # opps need to create
                    cur[node] = {}

    def rule_remove(self, rule):
        if '[]' in rule:
            raise ValueError('not supported') # FIXME

        rrule = self._rule_parse(rule)
        cur = self.root

        try:
            for node in rrule[:-1]:
                cur = cur[node]

            del cur[rrule[-1]]

        except KeyError:
            # nothing to delete
            pass

    def rule_set(self, rule, value):
        if '[]' in rule:
            raise ValueError('not supported') # FIXME

        rrule = self._rule_parse(rule)
        cur = self.root

        for node in rrule[:-1]:
            cur = cur[node]

        cur[rrule[-1]] = value

    def rule_str(self, rule):
        out = self.rule_search(rule)
        return out.replace('\n', '<br/>') if out else out


def wrap_uniq(wrapper_fn_name):
    " Wraps the output of the function with the specified function "
    # This is called when parsing "wrap_uniq('wrap_item')"

    def decorator(func):
        # This is called when parsing "@wrap_uniq('wrap_item')"

        def wrapped_func(self, *args, **kwargs):
            # This is called when the wrapped function is called

            output = func(self, *args, **kwargs)
            output_id = id(output)

            try:
                return self._map[output_id]

            except (KeyError, AttributeError):
                if not hasattr(self, '_map'):
                    self._map = {}

                wrapper_fn = getattr(self, wrapper_fn_name)
                obj = wrapper_fn(output)
                self._map[output_id] = obj

                return obj

        return wrapped_func

    return decorator


class Feed(object):
    itemsClass = property(lambda x: Item) # because Item is define below, i.e. afterwards
    dic = ('title', 'desc', 'items')

    title = property(
        lambda f:   f.get('title'),
        lambda f,x: f.set('title', x),
        lambda f:   f.rmv('title') )
    description = desc = property(
        lambda f:   f.get('desc'),
        lambda f,x: f.set('desc', x),
        lambda f:   f.rmv('desc') )
    items = property(
        lambda f:   f )

    def append(self, new=None):
        self.rule_create(self.rules['items'])
        item = self.items[-1]

        for attr in self.itemsClass.dic:
            try:
                setattr(item, attr, getattr(new, attr))

            except AttributeError:
                try:
                    setattr(item, attr, new[attr])

                except (IndexError, TypeError):
                    pass

        return item

    def wrap_item(self, item):
        return self.itemsClass(item, self.rules, self)

    @wrap_uniq('wrap_item')
    def __getitem__(self, key):
        return self.get_raw('items')[key]

    def __delitem__(self, key):
        self[key].remove()

    def __len__(self):
        return len(self.get_raw('items'))


class Item(object):
    dic = ('title', 'link', 'desc', 'content', 'time', 'updated')

    def __init__(self, xml=None, rules=None, parent=None):
        self._id = self._gen_id(xml)
        self.root = xml
        self.rules = rules
        self.parent = parent

    @staticmethod
    def _gen_id(xml=None, *args, **kwargs):
        return id(xml)

    title = property(
        lambda f:   f.get('item_title'),
        lambda f,x: f.set('item_title', x),
        lambda f:   f.rmv('item_title') )
    link = property(
        lambda f:   f.get('item_link'),
        lambda f,x: f.set('item_link', x),
        lambda f:   f.rmv('item_link') )
    description = desc = property(
        lambda f:   f.get('item_desc'),
        lambda f,x: f.set('item_desc', x),
        lambda f:   f.rmv('item_desc') )
    content = property(
        lambda f:   f.get('item_content'),
        lambda f,x: f.set('item_content', x),
        lambda f:   f.rmv('item_content') )
    time = property(
        lambda f:   f.time_prs(f.get('item_time')),
        lambda f,x: f.set('item_time', f.time_fmt(x)),
        lambda f:   f.rmv('item_time') )
    updated = property(
        lambda f:   f.time_prs(f.get('item_updated')),
        lambda f,x: f.set('item_updated', f.time_fmt(x)),
        lambda f:   f.rmv('item_updated') )


class ItemXML(Item, ParserXML):
    pass


class FeedXML(Feed, ParserXML):
    itemsClass = ItemXML

    def root_siblings(self):
        out = []
        current = self.root.getprevious()

        while current is not None:
            out.append(current)
            current = current.getprevious()

        return out

    def tostring(self, encoding='unicode', **k):
        # override needed due to "getroottree" inclusion
        # and to add stylesheet

        stylesheets = [x for x in self.root_siblings() if isinstance(x, etree.PIBase) and x.target == 'xml-stylesheet']

        for stylesheet in stylesheets:
            # remove all stylesheets present (be that ours or others')
            self.root.append(stylesheet) # needed as we can't delete root siblings https://stackoverflow.com/a/60232366
            self.root.remove(stylesheet)

        self.root.addprevious(etree.PI('xml-stylesheet', 'type="text/xsl" href="/sheet.xsl"'))

        return etree.tostring(self.root.getroottree(), encoding=encoding, method='xml', **k)


class ItemHTML(Item, ParserHTML):
    pass


class FeedHTML(Feed, ParserHTML):
    itemsClass = ItemHTML


class ItemJSON(Item, ParserJSON):
    def remove(self):
        rrule = self._rule_parse(self.rules['items'])
        cur = self.parent.root

        for node in rrule:
            if node == '[]':
                cur.remove(self.root)
                return

            cur = cur[node]

class FeedJSON(Feed, ParserJSON):
    itemsClass = ItemJSON


if __name__ == '__main__':
    import sys

    from . import crawler

    req = crawler.adv_get(sys.argv[1] if len(sys.argv) > 1 else 'https://www.nytimes.com/', follow='rss')
    feed = parse(req['data'], url=req['url'], encoding=req['encoding'])

    if sys.flags.interactive:
        print('>>> Interactive shell: try using `feed`')

    else:
        for item in feed.items:
            print(item.title, item.link)
