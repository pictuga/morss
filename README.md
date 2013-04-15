#Morss

This tool's goal is to get full-text RSS feeds out of striped RSS feeds, commonly available on internet. Indeed most newspapers only make a small description available to users in their rss feeds, which makes the RSS feed rather useless. So this tool intends to fix that problem.
This tool opens the links from the rss feed, then downloads the full article from the newspaper website and puts it back in the rss feed.

morss also has experimental support for Atom feeds.

##(xpath) Rules

To find the article content on the newspaper's website, morss need to know where to look at. The default target is the first `<h1>` element, since it's a common practice, or a `<article>` element, for HTML5 compliant websites.

However in some cases, these global rules are not working. Therefore custom xpath rules are needed. The proper way to input them to morss is detailed in the different use cases.

##Use cases
###Running on a server

For this, you need to make sure your host allows python script execution. This method uses HTTP calls to fetch the RSS feeds, such as `http://DOMAIN/MORSS/morss.py/feeds.bbci.co.uk/news/rss.xml`. Therefore the python script has to be accessible by the HTTP server.
This will require you to set `SERVER` to `True` at the top of the script.

Here, xpath rules stored in the `rules` file. (The name of the file can be changed in the script, in `class Feed`→`self.rulePath`. The file structure can be seen in the provided file. More details:

	Fancy name (description)(useless but not optional)
	http://example.com/path/to/the/rss/feed.xml
	http://example.co.uk/other/*/path/with/wildcard/*.xml
	//super/accurate[@xpath='expression']/..

As shown in the example, multiple urls can be specified for a single rule, so as to be able to match feeds from different locations of the website server (for example with or without "www."). Moreover feeds urls can be *NIX glob-style patterns, so as to match any feed from a website.

Works like a charm with Tiny Tiny RSS (<http://tt-rss.org/redmine/projects/tt-rss/wiki>).

###As a newsreader hook

To use it, the newsreader *Liferea* is required (unless other newsreaders provide the same kind of feature), since custom scripts can be run on top of the RSS feed, using its output as an RSS feed. (more: <http://lzone.de/liferea/scraping.htm>)

To use this script, you have to enable "postprocessing filter" in liferea feed settings, and to add `PATH/TO/MORSS/morss` as command to run.

For custom xpath rules, you have to add them in the command this way:

	PATH/TO/MORSS/morss "//custom[@xpath]/rule"

Quotes around the xpath rule are mandatory.

##Cache information

morss uses a small cache directory to make the loading faster. Given the way it's designed, the cache doesn't need to be purged each while and then, unless you stop following a big amount of feeds. Only in the case of mass un-subscribing, you might want to delete the cache files corresponding to the bygone feeds. If morss is running as a server, the cache folder is at `MORSS_DIRECTORY/cache/`, and in `$HOME/.cache/morss` otherwise.

##Extra configuration
###Length limitation

When parsing long feeds, with a lot of items (100+), morss might take a lot of time to parse it, or might even run into a memory overflow on some shared hosting plans (limits around 10Mb), in which case you might want to adjust the `self.max` value in `class Feed`. That value is the maximum number of items to parse. `0` means parse all items.

###Remove useless HTML elements

Unwanted HTML elements are also stripped from the article. By default, elements such as `<script>` and `<object>` are removed. Other elements can be specified, by adding them in the `self.trash` array in `class Feed`.

---

GPL3 licence.
Python **2.6**+ required (not 3).
