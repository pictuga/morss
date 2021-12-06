# Morss - Get full-text RSS feeds

[![Build Status](https://ci.pictuga.com/api/badges/pictuga/morss/status.svg)](https://ci.pictuga.com/pictuga/morss)

_GNU AGPLv3 code_  
_Provided logo is CC BY-NC-SA 4.0_

[Homepage](https://morss.it/) • 
[Upstream source code](https://git.pictuga.com/pictuga/morss) • 
[Github mirror](https://github.com/pictuga/morss) (for Issues & Pull requests)

[PyPI](https://pypi.org/project/morss/) • 
[Docker Hub](https://hub.docker.com/r/pictuga/morss)

This tool's goal is to get full-text RSS feeds out of striped RSS feeds,
commonly available on internet. Indeed most newspapers only make a small
description available to users in their rss feeds, which makes the RSS feed
rather useless. So this tool intends to fix that problem.

This tool opens the links from the rss feed, then downloads the full article
from the newspaper website and puts it back in the rss feed.

Morss also provides additional features, such as: .csv and json export, extended
control over output. A strength of morss is its ability to deal with broken
feeds, and to replace tracking links with direct links to the actual content.

Morss can also generate feeds from html and json files (see `feeds.py`), which
for instance makes it possible to get feeds for Facebook or Twitter, using
hand-written rules (ie. there's no automatic detection of links to build feeds).
Please mind that feeds based on html files may stop working unexpectedly, due to
html structure changes on the target website.

Additionally morss can detect rss feeds in html pages' `<meta>`.

You can use this program online for free at **[morss.it](https://morss.it/)**.

Some features of morss:

- Read RSS/Atom feeds
- Create RSS feeds from json/html pages
- Export feeds as RSS/JSON/CSV/HTML
- Fetch full-text content of feed items
- Follow 301/meta redirects
- Recover xml feeds with corrupt encoding
- Supports gzip-compressed http content
- HTTP caching with different backends (in-memory/sqlite/mysql/redis/diskcache)
- Works as server/cli tool
- Deobfuscate various tracking links

## Install

### Python package

Simple install (without optional dependencies)

From pip

```shell
pip install morss
```

From git

```shell
pip install git+https://git.pictuga.com/pictuga/morss.git
```

Full installation (including optional dependencies)

From pip

```shell
pip install morss[full]
```

From git

```shell
pip install git+https://git.pictuga.com/pictuga/morss.git#egg=morss[full]
```

The full install includes mysql, redis and diskcache (possible cache backends).
Otherwise, only in-memory and sqlite3 caches are available. The full install
also includes gunicorn and gevent (for more efficient HTTP handling).

The dependency `lxml` is fairly long to install (especially on Raspberry Pi, as
C code needs to be compiled). If possible on your distribution, try installing
it with the system package manager.

### Docker

From docker hub

With cli

```shell
docker pull pictuga/morss
```

With docker-compose

```yml
services:
    app:
        image: pictuga/morss
        ports:
            - '8000:8000'
```

Build from source

With cli

```shell
docker build --tag morss https://git.pictuga.com/pictuga/morss.git --no-cache --pull
```

With docker-compose

```yml
services:
    app:
        build: https://git.pictuga.com/pictuga/morss.git
        image: morss
        ports:
            - '8000:8000'
```

Then execute

```shell
docker-compose build --no-cache --pull
```

### Cloud providers

One-click deployment:

* [Heroku](https://heroku.com/deploy?template=https://github.com/pictuga/morss)
* [Google Cloud](https://deploy.cloud.run/?git_repo=https://github.com/pictuga/morss.git)

Providers supporting `cloud-init` (AWS, Oracle Cloud Infrastructure), based on Ubuntu:

``` yml
#cloud-config

packages:
  - python3-pip
  - python3-wheel
  - python3-lxml
  - git
  - ca-certificates

write_files:
  - path: /etc/environment
    content: |
      DEBUG=1
      CACHE=diskcache
      CACHE_SIZE=1073741824
  - path: /var/lib/cloud/scripts/per-boot/morss.sh
    permissions: 744
    content: |
      #!/bin/sh
      gunicorn --bind 0.0.0.0:${PORT:-8000} ${GUNICORN} --preload --access-logfile - --daemon morss

runcmd:
  - update-ca-certificates
  - iptables -I INPUT 6 -m state --state NEW -p tcp --dport {PORT:-8000} -j ACCEPT
  - netfilter-persistent save
  - pip install git+https://git.pictuga.com/pictuga/morss.git#egg=morss[full]
```

## Run

morss will auto-detect what "mode" to use.

### Running on/as a server

Set up the server as indicated below, then visit:

```
http://PATH/TO/MORSS/[main.py/][:argwithoutvalue[:argwithvalue=value[...]]]/FEEDURL
```

For example: `http://morss.example/:clip/https://twitter.com/pictuga`

*(Brackets indicate optional text)*

The `main.py` part is only needed if your server doesn't support the Apache
redirect rule set in the provided `.htaccess`.

Works like a charm with [Tiny Tiny RSS](https://tt-rss.org/), and most probably
other clients.


#### Using Docker

From docker hub

```shell
docker run -p 8000:8000 pictuga/morss
```

From source

```shell
docker run -p 8000:8000 morss
```

With docker-compose

```shell
docker-compose up
```

#### Using Gunicorn

```shell
gunicorn --preload morss
```

#### Using uWSGI

Running this command should do:

```shell
uwsgi --http :8000 --plugin python --wsgi-file main.py
```

#### Using morss' internal HTTP server

Morss can run its own, **very basic**, HTTP server, meant for debugging mostly.
The latter should start when you run morss without any argument, on port 8000.
I'd highly recommend you to use gunicorn or something similar for better
performance.

```shell
morss
```

You can change the port using environment variables like this `PORT=9000 morss`.

#### Via mod_cgi/FastCGI with Apache/nginx

For this, you'll want to change a bit the architecture of the files, for example
into something like this.

```
/
├── cgi
│   │
│   ├── main.py
│   ├── morss
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── morss.py
│   │   └── ...
│   │
│   ├── dateutil
│   └── ...
│
├── .htaccess
├── index.html
└── ...
```

For this, you need to make sure your host allows python script execution. This
method uses HTTP calls to fetch the RSS feeds, which will be handled through
`mod_cgi` for example on Apache severs.

Please pay attention to `main.py` permissions for it to be executable. Also
ensure that the provided `/www/.htaccess` works well with your server.

### As a CLI application

Run:

```
morss [--argwithoutvalue] [--argwithvalue=value] [...] FEEDURL
```

For example: `morss --clip http://feeds.bbci.co.uk/news/rss.xml`

*(Brackets indicate optional text)*

If using Docker:

```shell
docker run morss --clip http://feeds.bbci.co.uk/news/rss.xml
```

### As a newsreader hook

To use it, the newsreader [Liferea](http://lzone.de/liferea/) is required
(unless other newsreaders provide the same kind of feature), since custom
scripts can be run on top of the RSS feed, using its
[output](http://lzone.de/liferea/scraping.htm) as an RSS feed.

To use this script, you have to enable "(Unix) command" in liferea feed
settings, and use the command:

```
morss [--argwithoutvalue] [--argwithvalue=value] [...] FEEDURL
```

For example: `morss http://feeds.bbci.co.uk/news/rss.xml`

*(Brackets indicate optional text)*

### As a python library

Quickly get a full-text feed:

```python
>>> import morss
>>> xml_string = morss.process('http://feeds.bbci.co.uk/news/rss.xml')
>>> xml_string[:50]
"<?xml version='1.0' encoding='UTF-8'?>\n<?xml-style"
```

Using cache and passing arguments:

```python
>>> import morss
>>> url = 'http://feeds.bbci.co.uk/news/rss.xml'
>>> cache = '/tmp/morss-cache.db' # sqlite cache location
>>> options = {'csv':True}
>>> xml_string = morss.process(url, cache, options)
>>> xml_string[:50]
'{"title": "BBC News - Home", "desc": "The latest s'
```

`morss.process` is actually a wrapper around simpler function. It's still
possible to call the simpler functions, to have more control on what's happening
under the hood.

Doing it step-by-step:

```python
import morss, morss.crawler

url = 'http://newspaper.example/feed.xml'
options = morss.Options(csv=True) # arguments
morss.crawler.sqlite_default = '/tmp/morss-cache.db' # sqlite cache location

url, rss = morss.FeedFetch(url, options) # this only grabs the RSS feed
rss = morss.FeedGather(rss, url, options) # this fills the feed and cleans it up

output = morss.FeedFormat(rss, options, 'unicode') # formats final feed
```

## Arguments and settings

### Arguments

morss accepts some arguments, to lightly alter the output of morss. Arguments
may need to have a value (usually a string or a number). How to pass those
arguments to morss is explained in Run above.

The list of arguments can be obtained by running `morss --help`

```
usage: morss [-h] [--post STRING] [--xpath XPATH]
             [--format {rss,json,html,csv}] [--search STRING] [--clip]
             [--indent] [--cache] [--force] [--proxy] [--newest] [--firstlink]
             [--resolve] [--items XPATH] [--item_link XPATH]
             [--item_title XPATH] [--item_content XPATH] [--item_time XPATH]
             [--nolink] [--noref] [--silent]
             url

Get full-text RSS feeds

positional arguments:
  url                   feed url

optional arguments:
  -h, --help            show this help message and exit
  --post STRING         POST request
  --xpath XPATH         xpath rule to manually detect the article

output:
  --format {rss,json,html,csv}
                        output format
  --search STRING       does a basic case-sensitive search in the feed
  --clip                stick the full article content under the original feed
                        content (useful for twitter)
  --indent              returns indented XML or JSON, takes more place, but
                        human-readable

action:
  --cache               only take articles from the cache (ie. don't grab new
                        articles' content), so as to save time
  --force               force refetch the rss feed and articles
  --proxy               doesn't fill the articles
  --newest              return the feed items in chronological order (morss
                        ohterwise shows the items by appearing order)
  --firstlink           pull the first article mentioned in the description
                        instead of the default link
  --resolve             replace tracking links with direct links to articles
                        (not compatible with --proxy)

custom feeds:
  --items XPATH         (mandatory to activate the custom feeds function)
                        xpath rule to match all the RSS entries
  --item_link XPATH     xpath rule relative to items to point to the entry's
                        link
  --item_title XPATH    entry's title
  --item_content XPATH  entry's content
  --item_time XPATH     entry's date & time (accepts a wide range of time
                        formats)

misc:
  --nolink              drop links, but keeps links' inner text
  --noref               drop items' link
  --silent              don't output the final RSS (useless on its own, but
                        can be nice when debugging)

GNU AGPLv3 code
```

Further HTTP-only options:

- `callback=NAME`: for JSONP calls
- `cors`: allow Cross-origin resource sharing (allows XHR calls from other
servers)
- `txt`: changes the http content-type to txt (for faster "`view-source:`")

### Environment variables

To pass environment variables:

- Docker-cli: `docker run -p 8000:8000 morss --env KEY=value`
- docker-compose: add an `environment:` section in the .yml file
- Gunicorn/uWSGI/CLI: prepend `KEY=value` before the command
- Apache: via the `SetEnv` instruction (see sample `.htaccess` provided)

Generic:

- `DEBUG=1`: to have some feedback from the script execution. Useful for
debugging.
- `IGNORE_SSL=1`: to ignore SSL certs when fetch feeds and articles
- `DELAY` (seconds) sets the browser cache delay, only for HTTP clients
- `TIMEOUT` (seconds) sets the HTTP timeout when fetching rss feeds and articles

When parsing long feeds, with a lot of items (100+), morss might take a lot of
time to parse it, or might even run into a memory overflow on some shared
hosting plans (limits around 10Mb), in which case you might want to adjust the
below settings via environment variables.

Also, if the request takes too long to process, the http request might be
discarded. See relevant config for
[gunicorn](https://docs.gunicorn.org/en/stable/settings.html#timeout) or
[nginx](http://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout).

- `MAX_TIME` (seconds) sets the maximum amount of time spent *fetching*
articles, more time might be spent taking older articles from cache. `-1` for
unlimited.
- `MAX_ITEM` sets the maximum number of articles to fetch. `-1` for unlimited.
More articles will be taken from cache following the nexts settings.
- `LIM_TIME` (seconds) sets the maximum amount of time spent working on the feed
(whether or not it's already cached). Articles beyond that limit will be dropped
from the feed. `-1` for unlimited.
- `LIM_ITEM` sets the maximum number of article checked, limiting both the
number of articles fetched and taken from cache. Articles beyond that limit will
be dropped from the feed, even if they're cached. `-1` for unlimited.

morss uses caching to make loading faster. There are 3 possible cache backends:

- `(nothing/default)`: a simple python in-memory dict-like object.
- `CACHE=sqlite`: sqlite3 cache. Default file location is in-memory (i.e. it
will be cleared every time the program is run). Path can be defined with
`SQLITE_PATH`.
- `CACHE=mysql`: MySQL cache. Connection can be defined with the following
environment variables: `MYSQL_USER`, `MYSQL_PWD`, `MYSQL_DB`, `MYSQL_HOST`
- `CACHE=redis`: Redis cache. Connection can be defined with the following
environment variables: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PWD`
- `CACHE=diskcache`: disk-based cache. Target directory canbe defined with
`DISKCAHE_DIR`.

To limit the size of the cache:

- `CACHE_SIZE` sets the target number of items in the cache (further items will
be deleted but the cache might be temporarily bigger than that). Defaults to 1k
entries. NB. When using `diskcache`, this is the cache max size in Bytes.
- `CACHE_LIFESPAN` (seconds) sets how often the cache must be trimmed (i.e. cut
down to the number of items set in `CACHE_SIZE`). Defaults to 1min.

### Content matching

The content of articles is grabbed with our own readability fork. This means
that most of the time the right content is matched. However sometimes it fails,
therefore some tweaking is required. Most of the time, what has to be done is to
add some "rules" in the main script file in `readabilite.py` (not in morss).

Most of the time when hardly nothing is matched, it means that the main content
of the article is made of images, videos, pictures, etc., which readability
doesn't detect. Also, readability has some trouble to match content of very
small articles.

morss will also try to figure out whether the full content is already in place
(for those websites which understood the whole point of RSS feeds). However this
detection is very simple, and only works if the actual content is put in the
"content" section in the feed and not in the "summary" section.
