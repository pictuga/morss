#Morss

This tool's goal is to get full-text RSS feeds out of striped RSS feeds, commonly available on internet. Indeed most newspapers only make a small description available to users in their rss feeds, which makes the RSS feed rather useless. So this tool intends to fix that problem.
This tool opens the links from the rss feed, then downloads the full article from the newspaper website and puts it back in the rss feed.

morss also has experimental support for Atom feeds.

##Use cases

morss will auto-detect what "mode" to use.

###Running on a server

For this, you need to make sure your host allows python script execution. This method uses HTTP calls to fetch the RSS feeds, such as `http://DOMAIN/MORSS/morss.py/feeds.bbci.co.uk/news/rss.xml`. Therefore the python script has to be accessible by the HTTP server. With the `.htaccess` file provided, it's also possible, on APACHE servers, to access the filled feed at `http://DOMAIN/MORSS/feeds.bbci.co.uk/news/rss.xml` (without the `morss.py`).

Works like a charm with Tiny Tiny RSS (<http://tt-rss.org/redmine/projects/tt-rss/wiki>).

###As a newsreader hook

To use it, the newsreader *Liferea* is required (unless other newsreaders provide the same kind of feature), since custom scripts can be run on top of the RSS feed, using its output as an RSS feed. (more: <http://lzone.de/liferea/scraping.htm>)

To use this script, you have to enable "postprocessing filter" in liferea feed settings, and to add `PATH/TO/MORSS/morss` as command to run.

##Cache information

morss uses a small cache directory to make the loading faster. Given the way it's designed, the cache doesn't need to be purged each while and then, unless you stop following a big amount of feeds. Only in the case of mass un-subscribing, you might want to delete the cache files corresponding to the bygone feeds. If morss is running as a server, the cache folder is at `MORSS_DIRECTORY/cache/`, and in `$HOME/.cache/morss` otherwise.

##Extra configuration
###Length limitation

When parsing long feeds, with a lot of items (100+), morss might take a lot of time to parse it, or might even run into a memory overflow on some shared hosting plans (limits around 10Mb), in which case you might want to adjust the different values at the top of the script.

- `MAX_TIME` sets the maximum amount of time spent *fetching* articles, more time might be spent taking older articles from cache. `-1` for unlimited.
- `MAX_ITEM` sets the maximum number of articles to fetch. `0` for unlimited. More articles will be taken from cache following the next setting.
- `LIM_ITEM` sets the maximum number of article checked, limiting both the number of articles fetched and taken from cache. Articles beyond that limit will be dropped from the feed, even if they're cached. `0` for unlimited.

###Content matching

The content of articles is grabbed with a **readability** fork (see <https://github.com/buriy/python-readability>). This means that most of the time the right content is matched. However sometimes it fails, therefore some tweaking is required. Most of the time, what has to be done is to add some "rules" in the main script file in *readability* (not in morss).

Most of the time when hardly nothing is matched, it means that the main content of the article is made of images, videos, pictures, etc., which readability doesn't detect. Also, readability has some trouble to match content of very small articles.

morss will also try to figure out whether the full content is already in place (for those websites which understood the whole point of RSS feeds). However this detection is very simple, and only works if the actual content is put in the "content" section in the feed and not in the "summary" section.

---

GPL3 licence.
Python **2.6**+ required (not 3).
