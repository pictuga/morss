import pytest

from morss.crawler import *


def test_get(replay_server):
    assert get('http://localhost:8888/200-ok.txt') == b'success\r\n'

def test_adv_get(replay_server):
    assert adv_get('http://localhost:8888/200-ok.txt')['data'] == b'success\r\n'

@pytest.mark.parametrize('before,after', [
    (b'http://localhost:8888/',     'http://localhost:8888/'),
    ('localhost:8888/',             'http://localhost:8888/'),
    ('http:/localhost:8888/',       'http://localhost:8888/'),
    ('http://localhost:8888/&/',     'http://localhost:8888/&/'),
    ('http://localhost:8888/ /',    'http://localhost:8888/%20/'),
    ('http://localhost-€/€/',       'http://xn--localhost--077e/%E2%82%AC/'),
    ('http://localhost-€:8888/€/',  'http://xn--localhost--077e:8888/%E2%82%AC/'),
    ])
def test_sanitize_url(before, after):
    assert sanitize_url(before) == after

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(SizeLimitHandler(500*1024))])
def test_size_limit_handler(replay_server, opener):
    assert len(opener.open('http://localhost:8888/size-1MiB.txt').read()) == 500*1024

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(GZIPHandler())])
def test_gzip_handler(replay_server, opener):
    assert opener.open('http://localhost:8888/gzip.txt').read() == b'success\n'

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(EncodingFixHandler())])
@pytest.mark.parametrize('url', [
    'enc-gb2312-header.txt', 'enc-gb2312-meta.txt', #'enc-gb2312-missing.txt',
    'enc-iso-8859-1-header.txt', 'enc-iso-8859-1-missing.txt',
    'enc-utf-8-header.txt',
    ])
def test_encoding_fix_handler(replay_server, opener, url):
    out = adv_get('http://localhost:8888/%s' % url)
    out = out['data'].decode(out['encoding'])
    assert 'succes' in out or 'succès' in out or '成功' in out

@pytest.mark.parametrize('opener', [custom_opener(follow='rss'), build_opener(AlternateHandler(MIMETYPE['rss']))])
def test_alternate_handler(replay_server, opener):
    assert opener.open('http://localhost:8888/alternate-abs.txt').geturl() == 'http://localhost:8888/200-ok.txt'

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(HTTPEquivHandler(), HTTPRefreshHandler())])
def test_http_equiv_handler(replay_server, opener):
    assert opener.open('http://localhost:8888/meta-redirect-abs.txt').geturl() == 'http://localhost:8888/200-ok.txt'
    assert opener.open('http://localhost:8888/meta-redirect-rel.txt').geturl() == 'http://localhost:8888/200-ok.txt'
    assert opener.open('http://localhost:8888/meta-redirect-url.txt').geturl() == 'http://localhost:8888/200-ok.txt'

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(HTTPAllRedirectHandler())])
def test_http_all_redirect_handler(replay_server, opener):
    assert opener.open('http://localhost:8888/308-redirect.txt').geturl() == 'http://localhost:8888/200-ok.txt'
    assert opener.open('http://localhost:8888/301-redirect-abs.txt').geturl() == 'http://localhost:8888/200-ok.txt'
    assert opener.open('http://localhost:8888/301-redirect-rel.txt').geturl() == 'http://localhost:8888/200-ok.txt'
    assert opener.open('http://localhost:8888/301-redirect-url.txt').geturl() == 'http://localhost:8888/200-ok.txt'

@pytest.mark.parametrize('opener', [custom_opener(), build_opener(HTTPRefreshHandler())])
def test_http_refresh_handler(replay_server, opener):
    assert opener.open('http://localhost:8888/header-refresh.txt').geturl() == 'http://localhost:8888/200-ok.txt'
