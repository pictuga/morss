#Morss - Get full-text RSS feeds

This tool's goal is to get full-text RSS feeds out of striped RSS feeds, commonly available on internet. Indeed most newspapers only make a small description available to users in their rss feeds, which makes the RSS feed rather useless. So this tool intends to fix that problem.
This tool opens the links from the rss feed, then downloads the full article from the newspaper website and puts it back in the rss feed.

Morss also provides additional features, such as: .csv and json export, extended control over output. A strength of morss is its ability to deal with broken feeds, and to replace tracking links with direct links to the actual content.
Morss can also generate feeds from html and json files (see `feedify.py`), which for instance makes it possible to get feeds for Facebook or Twitter, using hand-written rules (ie. there's no automatic detection of links to build feeds). Please mind that feeds based on html files may stop working unexpectedly, due to html structure changes on the target website.
Additionally morss can grab the source xml feed of iTunes podcast, and detect rss feeds in html pages' `<meta>`.

You can use this program online for free at **[morss.it](http://morss.it/)** (there's also a [test](http://test.morss.it/) version).

##Dependencies

You do need:
- [python](http://www.python.org/) >= 2.6 < 3
- [lxml](http://lxml.de/) for xml parsing
- [this](https://github.com/buriy/python-readability) readability fork
- [dateutil](http://labix.org/python-dateutil) to parse feed dates
- [html2text](http://www.aaronsw.com/2002/html2text/)
- [OrderedDict](https://pypi.python.org/pypi/ordereddict) if using python < 2.7

You may also need:
- Apache, with python-cgi support, to run on a server
- a fast internet connection

GPL3 code.

##Arguments

morss accepts some arguments, to lightly alter the output of morss. Arguments are all boolean. In the different "Use cases" below is detailed how to pass those arguments to morss.

The arguments are:

- Change what morss does
	- `json`: output as JSON  
	`indent`: returns indented JSON, takes more place, but human-readable
	- `proxy`: doesn't fill the articles
	- `clip`: stick the full article content under the original feed content (useful for twitter)
	- `keep`: by default, morss does drop feed description whenever the full-content is found (so as not to mislead users who use Firefox, since the latter only shows the description in the feed preview, so they might believe morss doens't work), but with this argument, the description is kept
- Advanced
	- `csv`: export to csv
	- `md`: convert articles to Markdown
	- `cache`: only take articles from the cache (ie. don't grab new articles' content), so as to save time
	- `debug`: to have some feedback from the script execution. Useful for debugging
	- `theforce`: force download the rss feed
	- `silent`: don't output the final RSS (useless on its own, but can be nice when debugging)
- http server only
	- `html`: changes the http content-type to html, so that python cgi erros (written in html) are readable in a web browser
	- `txt`: changes the http content-type to txt (for faster "`view-source:`")
	- `force`: avoid using your browser cache (do not support 304 errors)

##Use cases

morss will auto-detect what "mode" to use.

###Running on a server

To achieve this, you will have to move the files of `/morss/` and of `/www/` into one single folder.

####With Apache, nginx, lighttpd and others

For this, you need to make sure your host allows python script execution. This method uses HTTP calls to fetch the RSS feeds, which will be handled through `mod_cgi` for example on Apache severs.

Please pay attention to `/www/morss.py` permissions for it to be executable. Also ensure that the provided `/www/.htaccess` works well with your server.

####Using morss' internal HTTP server

Morss can run its own HTTP server. The later should start when you run morss without any argument, on port 8080. For now, you have to change the hardcoded port if you want to change it.

####Passing arguments

Then visit: **`http://PATH/TO/MORSS/[morss.py/][:argwithoutvalue[...]]/FEEDURL`**  
For example: `http://morss.example/:clip/https://twitter.com/pictuga`  
*(Brackets indicate optional text)*

The `morss.py` part is only needed if your server doesn't support the Apache redirect rule set in the provided `.htaccess`.

Works like a charm with [Tiny Tiny RSS](http://tt-rss.org/redmine/projects/tt-rss/wiki), and most probably other clients.

###As a CLI application

Run: **`[python2.7] morss.py [argwithoutvalue] [...] FEEDURL`**  
For example: `python2.7 morss.py debug http://feeds.bbci.co.uk/news/rss.xml`  
*(Brackets indicate optional text)*

###As a newsreader hook

To use it, the newsreader [Liferea](http://lzone.de/liferea/) is required (unless other newsreaders provide the same kind of feature), since custom scripts can be run on top of the RSS feed, using its [output](http://lzone.de/liferea/scraping.htm) as an RSS feed.

To use this script, you have to enable "(Unix) command" in liferea feed settings, and use the command: **`[python2.7] PATH/TO/MORSS/morss.py [argwithoutvalue] [...] FEEDURL`**  
For example: `python2.7 PATH/TO/MORSS/morss.py http://feeds.bbci.co.uk/news/rss.xml`  
*(Brackets indicate optional text)*

###As a python library

The code was not optimized to be used as a library. However here is a quick draft of what your code should look like if you intend to use morss as a library. This requires a lot of function calls, to have fine control over the different steps.

```python
import morss

url = 'http://newspaper.example/feed.xml'
options = morss.Options(['force', 'quiet']) # arguments
cache_path = '/tmp/morss-cache' # cache folder, needs write permission

url, cache = morss.Init(url, cache_path, options) # properly create folders and objects
rss = morss.Fetch(url, cache, options) # this only grabs the RSS feed
rss = morss.Gather(rss, url, cache, options) # this fills the feed and cleans it up

output = morss.After(rss, options) # formats final feed
```

##Cache information

morss uses a small cache directory to make the loading faster. Given the way it's designed, the cache doesn't need to be purged each while and then, unless you stop following a big amount of feeds. Only in the case of mass un-subscribing, you might want to delete the cache files corresponding to the bygone feeds. If morss is running as a server, the cache folder is at `MORSS_DIRECTORY/cache/`, and in `$HOME/.cache/morss` otherwise.

##Configuration
###Length limitation

When parsing long feeds, with a lot of items (100+), morss might take a lot of time to parse it, or might even run into a memory overflow on some shared hosting plans (limits around 10Mb), in which case you might want to adjust the different values at the top of the script.

- `MAX_TIME` sets the maximum amount of time spent *fetching* articles, more time might be spent taking older articles from cache. `-1` for unlimited.
- `MAX_ITEM` sets the maximum number of articles to fetch. `-1` for unlimited. More articles will be taken from cache following the nexts settings.
- `LIM_TIME` sets the maximum amount of time spent working on the feed (whether or not it's already cached). Articles beyond that limit will be dropped from the feed. `-1` for unlimited.
- `LIM_ITEM` sets the maximum number of article checked, limiting both the number of articles fetched and taken from cache. Articles beyond that limit will be dropped from the feed, even if they're cached. `-1` for unlimited.

###Other settings

- `DELAY` sets the browser cache delay, only for HTTP clients
- `TIMEOUT` sets the HTTP timeout when fetching rss feeds and articles
- `THREADS` sets the number of threads to use. `1` makes no use of multithreading.

###Content matching

The content of articles is grabbed with a [**readability** fork](https://github.com/buriy/python-readability). This means that most of the time the right content is matched. However sometimes it fails, therefore some tweaking is required. Most of the time, what has to be done is to add some "rules" in the main script file in *readability* (not in morss).

Most of the time when hardly nothing is matched, it means that the main content of the article is made of images, videos, pictures, etc., which readability doesn't detect. Also, readability has some trouble to match content of very small articles.

morss will also try to figure out whether the full content is already in place (for those websites which understood the whole point of RSS feeds). However this detection is very simple, and only works if the actual content is put in the "content" section in the feed and not in the "summary" section.

***

##Todo

You can contribute to this projet. If you're not sure what to do, you can pick from this list:

- Add ability to run morss.py as an update daemon
- Rewrite the readability fork, for better performances, and make it more "pythonic" (Firefox for Android may have it's own implementation, most probably cleaner than `readability.js`')
