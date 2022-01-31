import pytest

from morss.crawler import adv_get
from morss.feeds import *


def get_feed(url):
    url = 'http://localhost:8888/%s' % url
    out = adv_get(url)
    feed = parse(out['data'], url=url, encoding=out['encoding'])
    return feed

def check_feed(feed):
    # NB. time and updated not covered
    assert feed.title == '!TITLE!'
    assert feed.desc == '!DESC!'
    assert feed[0] == feed.items[0]
    assert feed[0].title == '!ITEM_TITLE!'
    assert feed[0].link == '!ITEM_LINK!'
    assert '!ITEM_DESC!' in feed[0].desc # broader test due to possible inclusion of surrounding <div> in xml
    assert '!ITEM_CONTENT!' in feed[0].content

def check_output(feed):
    output = feed.tostring()
    assert '!TITLE!' in output
    assert '!DESC!' in output
    assert '!ITEM_TITLE!' in output
    assert '!ITEM_LINK!' in output
    assert '!ITEM_DESC!' in output
    assert '!ITEM_CONTENT!' in output

def check_change(feed):
    feed.title = '!TITLE2!'
    feed.desc = '!DESC2!'
    feed[0].title = '!ITEM_TITLE2!'
    feed[0].link = '!ITEM_LINK2!'
    feed[0].desc = '!ITEM_DESC2!'
    feed[0].content = '!ITEM_CONTENT2!'

    assert feed.title == '!TITLE2!'
    assert feed.desc == '!DESC2!'
    assert feed[0].title == '!ITEM_TITLE2!'
    assert feed[0].link == '!ITEM_LINK2!'
    assert '!ITEM_DESC2!' in feed[0].desc
    assert '!ITEM_CONTENT2!' in feed[0].content

def check_add(feed):
    feed.append({
        'title': '!ITEM_TITLE3!',
        'link': '!ITEM_LINK3!',
        'desc': '!ITEM_DESC3!',
        'content': '!ITEM_CONTENT3!',
    })

    assert feed[1].title == '!ITEM_TITLE3!'
    assert feed[1].link == '!ITEM_LINK3!'
    assert '!ITEM_DESC3!' in feed[1].desc
    assert '!ITEM_CONTENT3!' in feed[1].content

each_format = pytest.mark.parametrize('url', [
    'feed-rss-channel-utf-8.txt', 'feed-atom-utf-8.txt',
    'feed-atom03-utf-8.txt', 'feed-json-utf-8.txt', 'feed-html-utf-8.txt',
    ])

each_check = pytest.mark.parametrize('check', [
    check_feed, check_output, check_change, check_add,
    ])

@each_format
@each_check
def test_parse(replay_server, url, check):
    feed = get_feed(url)
    check(feed)

@each_format
@each_check
def test_convert_rss(replay_server, url, check):
    feed = get_feed(url)
    feed = feed.convert(FeedXML)
    check(feed)

@each_format
@each_check
def test_convert_json(replay_server, url, check):
    feed = get_feed(url)
    feed = feed.convert(FeedJSON)
    check(feed)

@each_format
@each_check
def test_convert_html(replay_server, url, check):
    feed = get_feed(url)
    feed = feed.convert(FeedHTML)
    if len(feed) > 1:
        # remove the 'blank' default html item
        del feed[0]
    check(feed)

@each_format
def test_convert_csv(replay_server, url):
    # only csv output, not csv feed, check therefore differnet
    feed = get_feed(url)
    output = feed.tocsv()

    assert '!ITEM_TITLE!' in output
    assert '!ITEM_LINK!' in output
    assert '!ITEM_DESC!' in output
    assert '!ITEM_CONTENT!' in output
