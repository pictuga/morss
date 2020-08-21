import sys
import os.path

from . import crawler
from .morss import FeedFetch, FeedGather, FeedFormat
from .morss import Options, filterOptions, parseOptions
from .morss import log, DEBUG


def cli_app():
    options = Options(filterOptions(parseOptions(sys.argv[1:-1])))
    url = sys.argv[-1]

    global DEBUG
    DEBUG = options.debug

    crawler.default_cache = crawler.SQLiteCache(os.path.expanduser('~/.cache/morss-cache.db'))

    url, rss = FeedFetch(url, options)
    rss = FeedGather(rss, url, options)
    out = FeedFormat(rss, options, 'unicode')

    if not options.silent:
        print(out)

    log('done')
