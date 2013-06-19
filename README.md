#Morss - Get ful text RSS feeds

This tool's goal is to get full-text RSS feeds out of striped RSS feeds, commonly available on internet. Indeed most newspapers only make a small description available to users in their rss feeds, which makes the RSS feed rather useless. So this tool intends to fix that problem.
This tool opens the links from the rss feed, then downloads the full article from the newspaper website and puts it back in the rss feed.

You can use this program online for free at **<http://morss.it/>**.

##Dependencies

You do need:
- [python](http://www.python.org/) >= 2.6
- [lxml](http://lxml.de/) for xml parsing
- this [readability](https://github.com/buriy/python-readability) fork

You may also need:
- Apache, with python-cgi support, to run on a server
- a fast internet connection

##Usecases

morss will auto-detect what "mode" to use.

###Running on a server

For this, you need to make sure your host allows python script execution. This method uses HTTP calls to fetch the RSS feeds, such as `http://DOMAIN/MORSS/morss.py/feeds.bbci.co.uk/news/rss.xml`. Therefore the python script has to be accessible by the HTTP server. With the `.htaccess` file provided, it's also possible, on APACHE servers, to access the filled feed at `http://DOMAIN/MORSS/feeds.bbci.co.uk/news/rss.xml` (without the `morss.py`).

**NB.** Morss **DOESN'T** provide any HTTP server itself. This must be done with Apache or nginx with python support!

Works like a charm with [Tiny Tiny RSS](http://tt-rss.org/redmine/projects/tt-rss/wiki).

###As a newsreader hook

To use it, the newsreader [Liferea](http://lzone.de/liferea/) is required (unless other newsreaders provide the same kind of feature), since custom scripts can be run on top of the RSS feed, using its [output](http://lzone.de/liferea/scraping.htm) as an RSS feed.

To use this script, you have to enable "(Unix) command" in liferea feed settings, and use the command `PATH/TO/MORSS/morss.py http://path/to/feed.xml`.

##Cache information

morss uses a small cache directory to make the loading faster. Given the way it's designed, the cache doesn't need to be purged each while and then, unless you stop following a big amount of feeds. Only in the case of mass un-subscribing, you might want to delete the cache files corresponding to the bygone feeds. If morss is running as a server, the cache folder is at `MORSS_DIRECTORY/cache/`, and in `$HOME/.cache/morss` otherwise.

##Extra configuration
###Length limitation

When parsing long feeds, with a lot of items (100+), morss might take a lot of time to parse it, or might even run into a memory overflow on some shared hosting plans (limits around 10Mb), in which case you might want to adjust the different values at the top of the script.

- `MAX_TIME` sets the maximum amount of time spent *fetching* articles, more time might be spent taking older articles from cache. `-1` for unlimited.
- `MAX_ITEM` sets the maximum number of articles to fetch. `0` for unlimited. More articles will be taken from cache following the next setting.
- `LIM_ITEM` sets the maximum number of article checked, limiting both the number of articles fetched and taken from cache. Articles beyond that limit will be dropped from the feed, even if they're cached. `0` for unlimited.

###Content matching

The content of articles is grabbed with a [**readability** fork](https://github.com/buriy/python-readability). This means that most of the time the right content is matched. However sometimes it fails, therefore some tweaking is required. Most of the time, what has to be done is to add some "rules" in the main script file in *readability* (not in morss).

Most of the time when hardly nothing is matched, it means that the main content of the article is made of images, videos, pictures, etc., which readability doesn't detect. Also, readability has some trouble to match content of very small articles.

morss will also try to figure out whether the full content is already in place (for those websites which understood the whole point of RSS feeds). However this detection is very simple, and only works if the actual content is put in the "content" section in the feed and not in the "summary" section.

##Todo

You can contribute to this projet. If you're not sure what to do, you can pick from this list:

- Add ability to run HTTP server within morss.py
- Add ability to run morss.py as an update daemon

---

GPL3 licence.
Python **2.6**+ required (not 3).
