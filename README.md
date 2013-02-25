#Morss

This tool's goal is to get full-text rss feeds out of striped rss feeds, commonly available on internet. Indeed most newspapers only make a small description available to users in their rss feeds, which makes the rss feed rather useless. So this tool intends to fix that problem.
This tool opens the links from the rss feed, then downloads the full article from the newspaper website and puts it back in the rss feed.

To use it, the rss reader *Liferea* is required (unless other rss readers provide the same kind of feature), since custom scripts can be run on top of the rss feed, using its output as an rss feed. (more: <http://lzone.de/liferea/scraping.htm>)

To use this script, you have to enable "postprocessing filter" in liferea feed settings, and to add the following line as command to run:

	morss "RULE"

And you have to replace **RULE** with a proper rule, which has to be a proper xpath instruction, matching the main content of the website. Some rules example are given in the "rules" file. You have to keep the " " aroung the rule. If the parameter is omitted, `//h1/..` is used instead. This default rule works on a lot of websites, since it's a common practice for search engine optimization.

Using this, rss refresh tends to be a bit slower, but caching helps a lot for frequent updates.
