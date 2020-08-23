import sys
import os.path
import argparse

from . import crawler
from .morss import FeedFetch, FeedGather, FeedFormat
from .morss import Options
from .morss import log


def cli_app():
    parser = argparse.ArgumentParser(
        prog='morss',
        description='Get full-text RSS feeds',
        epilog='GNU AGPLv3 code'
        )

    parser.add_argument('url', help='feed url')

    group = parser.add_argument_group('output')
    group.add_argument('--format', default='rss', choices=('rss', 'json', 'html', 'csv'), help='output format')
    group.add_argument('--search', action='store', type=str, metavar='STRING', help='does a basic case-sensitive search in the feed')
    group.add_argument('--clip', action='store_true', help='stick the full article content under the original feed content (useful for twitter)')
    group.add_argument('--indent', action='store_true', help='returns indented XML or JSON, takes more place, but human-readable')

    group = parser.add_argument_group('action')
    group.add_argument('--cache', action='store_true', help='only take articles from the cache (ie. don\'t grab new articles\' content), so as to save time')
    group.add_argument('--force', action='store_true', help='force refetch the rss feed and articles')
    group.add_argument('--proxy', action='store_true', help='doesn\'t fill the articles')
    group.add_argument('--newest', action='store_true', help='return the feed items in chronological order (morss ohterwise shows the items by appearing order)')
    group.add_argument('--firstlink', action='store_true', help='pull the first article mentioned in the description instead of the default link')

    group = parser.add_argument_group('custom feeds')
    group.add_argument('--items', action='store', type=str, metavar='XPATH', help='(mandatory to activate the custom feeds function) xpath rule to match all the RSS entries')
    group.add_argument('--item_link', action='store', type=str, metavar='XPATH', help='xpath rule relative to items to point to the entry\'s link')
    group.add_argument('--item_title', action='store', type=str, metavar='XPATH', help='entry\'s title')
    group.add_argument('--item_content', action='store', type=str, metavar='XPATH', help='entry\'s content')
    group.add_argument('--item_time', action='store', type=str, metavar='XPATH', help='entry\'s date & time (accepts a wide range of time formats)')

    group = parser.add_argument_group('misc')
    group.add_argument('--nolink', action='store_true', help='drop links, but keeps links\' inner text')
    group.add_argument('--noref', action='store_true', help='drop items\' link')
    group.add_argument('--silent', action='store_true', help='don\'t output the final RSS (useless on its own, but can be nice when debugging)')

    options = Options(parser.parse_args())
    url = options.url

    global DEBUG
    DEBUG = options.debug

    crawler.default_cache = crawler.SQLiteCache(os.path.expanduser('~/.cache/morss-cache.db'))

    url, rss = FeedFetch(url, options)
    rss = FeedGather(rss, url, options)
    out = FeedFormat(rss, options, 'unicode')

    if not options.silent:
        print(out)

    log('done')
