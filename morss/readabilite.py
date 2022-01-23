# This file is part of morss
#
# Copyright (C) 2013-2020 pictuga <contact@pictuga.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.

import re

import bs4.builder._lxml
import lxml.etree
import lxml.html
import lxml.html.soupparser


class CustomTreeBuilder(bs4.builder._lxml.LXMLTreeBuilder):
    def default_parser(self, encoding):
        return lxml.html.HTMLParser(target=self, remove_comments=True, remove_pis=True, encoding=encoding)


def parse(data, encoding=None):
    kwargs = {'from_encoding': encoding} if encoding else {}
    return lxml.html.soupparser.fromstring(data, builder=CustomTreeBuilder, **kwargs)


def count_words(string):
    """ Quick word count

    Simply assumes that all words are 5 letter long.
    And so in about every language (sorry chinese).
    Basically skips spaces in the count. """

    if string is None:
        return 0

    string = string.strip()

    i = 0
    count = 0

    try:
        while True:
            if string[i] not in "\r\n\t ":
                count += 1
                i += 6
            else:
                i += 1
    except IndexError:
        pass

    return count


def count_content(node):
    # count words and imgs
    return count_words(node.text_content()) + len(node.findall('.//img'))


class_bad = ['comment', 'community', 'extra', 'foot',
    'sponsor', 'pagination', 'pager', 'tweet', 'twitter', 'com-', 'masthead',
    'media', 'meta', 'related', 'shopping', 'tags', 'tool', 'author', 'about',
    'head', 'robots-nocontent', 'combx', 'disqus', 'menu', 'remark', 'rss',
    'shoutbox', 'sidebar', 'ad-', 'agegate', 'popup', 'sharing', 'share',
    'social', 'contact', 'footnote', 'outbrain', 'promo', 'scroll', 'hidden',
    'widget', 'hide']

regex_bad = re.compile('|'.join(class_bad), re.I)

class_good = ['and', 'article', 'body', 'column', 'main',
    'shadow', 'content', 'entry', 'hentry', 'main', 'page', 'pagination',
    'post', 'text', 'blog', 'story', 'par', 'editorial']

regex_good = re.compile('|'.join(class_good), re.I)


tags_dangerous = ['script', 'head', 'iframe', 'object', 'style', 'link', 'meta']

tags_junk = tags_dangerous + ['noscript', 'param', 'embed', 'layer', 'applet',
    'form', 'input', 'textarea', 'button', 'footer']

tags_bad = tags_junk + ['a', 'aside']

tags_good = ['h1', 'h2', 'h3', 'article', 'p', 'cite', 'section', 'figcaption',
    'figure', 'em', 'strong', 'pre', 'br', 'hr', 'headline']

tags_meaning = ['a', 'abbr', 'address', 'acronym', 'audio', 'article', 'aside',
    'b', 'bdi', 'bdo', 'big', 'blockquote', 'br', 'caption', 'cite', 'center',
    'code', 'col', 'colgroup', 'data', 'dd', 'del', 'details', 'description',
    'dfn', 'dl', 'font', 'dt', 'em', 'figure', 'figcaption', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'main', 'mark',
    'nav', 'ol', 'p', 'pre', 'q', 'ruby', 'rp', 'rt', 's', 'samp', 'small',
    'source', 'strike', 'strong', 'sub', 'summary', 'sup', 'table', 'tbody',
    'td', 'tfoot', 'th', 'thead', 'time', 'tr', 'track', 'tt', 'u', 'ul', 'var',
    'wbr', 'video']
    # adapted from tt-rss source code, to keep even as shells

tags_void = ['img', 'hr', 'br'] # to keep even if empty


attributes_fine = ['title', 'src', 'href', 'type', 'value']


def score_node(node):
    " Score individual node "

    score = 0
    class_id = (node.get('class') or '') + (node.get('id') or '')

    if (isinstance(node, lxml.html.HtmlComment)
            or isinstance(node, lxml.html.HtmlProcessingInstruction)):
        return 0

    if node.tag in tags_dangerous:
        return 0

    if node.tag in tags_junk:
        score += -1 # actuall -2 as tags_junk is included tags_bad

    if node.tag in tags_bad:
        score += -1

    if regex_bad.search(class_id):
        score += -1

    if node.tag in tags_good:
        score += 4

    if regex_good.search(class_id):
        score += 3

    wc = count_words(node.text_content())

    score += min(int(wc/10), 3) # give 1pt bonus for every 10 words, max of 3

    if wc != 0:
        wca = count_words(' '.join([x.text_content() for x in node.findall('.//a')]))
        score = score * ( 1 - 2 * float(wca)/wc )

    return score


def score_all(node):
    " Fairly dumb loop to score all worthwhile nodes. Tries to be fast "

    for child in node:
        score = score_node(child)
        set_score(child, score, 'morss_own_score')

        if score > 0 or len(list(child.iterancestors())) <= 2:
            spread_score(child, score)
            score_all(child)


def set_score(node, value, label='morss_score'):
    try:
        node.attrib[label] = str(float(value))

    except KeyError:
        # catch issues with e.g. html comments
        pass


def get_score(node):
    return float(node.attrib.get('morss_score', 0))


def incr_score(node, delta):
    set_score(node, get_score(node) + delta)


def get_all_scores(node):
    return {x:get_score(x) for x in list(node.iter()) if get_score(x) != 0}


def spread_score(node, score):
    " Spread the node's score to its parents, on a linear way "

    delta = score / 2

    for ancestor in [node,] + list(node.iterancestors()):
        if score >= 1 or ancestor is node:
            incr_score(ancestor, score)

            score -= delta

        else:
            break


def clean_root(root, keep_threshold=None):
    for node in list(root):
        # bottom-up approach, i.e. starting with children before cleaning current node
        clean_root(node, keep_threshold)
        clean_node(node, keep_threshold)


def clean_node(node, keep_threshold=None):
    parent = node.getparent()

    # remove comments
    if (isinstance(node, lxml.html.HtmlComment)
            or isinstance(node, lxml.html.HtmlProcessingInstruction)):
        parent.remove(node)
        return

    if parent is None:
        # this is <html/> (or a removed element waiting for GC)
        return

    # remove dangerous tags, no matter what
    if node.tag in tags_dangerous:
        parent.remove(node)
        return

    # high score, so keep
    if keep_threshold is not None and keep_threshold > 0 and get_score(node) >= keep_threshold:
        return

    gdparent = parent.getparent()

    # remove shitty tags
    if node.tag in tags_junk:
        parent.remove(node)
        return

    # remove shitty class/id FIXME TODO too efficient, might want to add a toggle
    class_id = node.get('class', '') + node.get('id', '')
    if len(regex_bad.findall(class_id)) >= 2:
        node.getparent().remove(node)
        return

    # remove shitty link
    if node.tag == 'a' and len(list(node.iter())) > 3:
        parent.remove(node)
        return

    # remove if too many kids & too high link density
    wc = count_words(node.text_content())
    if wc != 0 and len(list(node.iter())) > 3:
        wca = count_words(' '.join([x.text_content() for x in node.findall('.//a')]))
        if float(wca)/wc > 0.8:
            parent.remove(node)
            return

    # squash text-less elements shells
    if node.tag in tags_void:
        # keep 'em
        pass
    elif node.tag in tags_meaning:
        # remove if content-less
        if not count_content(node):
            parent.remove(node)
            return
    else:
        # squash non-meaningful if no direct text
        content = (node.text or '') + ' '.join([child.tail or '' for child in node])
        if not count_words(content):
            node.drop_tag()
            return

    # for http://vice.com/fr/
    if node.tag == 'img' and 'data-src' in node.attrib:
        node.attrib['src'] = node.attrib['data-src']

    # clean the node's attributes
    for attrib in node.attrib:
        if attrib not in attributes_fine:
            del node.attrib[attrib]

    # br2p
    if node.tag == 'br':
        if gdparent is None:
            return

        if not count_words(node.tail):
            # if <br/> is at the end of a div (to avoid having <p/>)
            return

        else:
            # set up new node
            new_node = lxml.html.Element(parent.tag)
            new_node.text = node.tail

            for child in node.itersiblings():
                new_node.append(child)

            # delete br
            node.tail = None
            parent.remove(node)

            gdparent.insert(gdparent.index(parent)+1, new_node)


def lowest_common_ancestor(node_a, node_b, max_depth=None):
    ancestors_a = list(node_a.iterancestors())
    ancestors_b = list(node_b.iterancestors())

    if max_depth is not None:
        ancestors_a = ancestors_a[:max_depth]
        ancestors_b = ancestors_b[:max_depth]

    ancestors_a.insert(0, node_a)
    ancestors_b.insert(0, node_b)

    for ancestor_a in ancestors_a:
        if ancestor_a in ancestors_b:
            return ancestor_a

    return node_a # should always find one tho, at least <html/>, but needed for max_depth


def get_best_node(html, threshold=5):
    # score all nodes
    score_all(html)

    # rank all nodes (largest to smallest)
    ranked_nodes = sorted(html.iter(), key=lambda x: get_score(x), reverse=True)

    # minimum threshold
    if not len(ranked_nodes) or get_score(ranked_nodes[0]) < threshold:
        return None

    # take common ancestor or the two highest rated nodes
    if len(ranked_nodes) > 1:
        best = lowest_common_ancestor(ranked_nodes[0], ranked_nodes[1], 3)

    else:
        best = ranked_nodes[0]

    return best


def get_article(data, url=None, encoding_in=None, encoding_out='unicode', debug=False, threshold=5, xpath=None):
    " Input a raw html string, returns a raw html string of the article "

    html = parse(data, encoding_in)

    if xpath is not None:
        xpath_match = html.xpath(xpath)

        if len(xpath_match):
            best = xpath_match[0]

        else:
            best = get_best_node(html, threshold)

    else:
        best = get_best_node(html, threshold)

    if best is None:
        # if threshold not met
        return None

    # clean up
    if not debug:
        keep_threshold = get_score(best) * 3/4
        clean_root(best, keep_threshold)

    # check for spammy content (links only)
    wc = count_words(best.text_content())
    wca = count_words(' '.join([x.text_content() for x in best.findall('.//a')]))

    if not debug and (wc - wca < 50 or float(wca) / wc > 0.3):
        return None

    # fix urls
    if url:
        best.make_links_absolute(url)

    return lxml.etree.tostring(best if not debug else html, method='html', encoding=encoding_out)


if __name__ == '__main__':
    import sys

    from . import crawler

    req = crawler.adv_get(sys.argv[1] if len(sys.argv) > 1 else 'https://morss.it')
    article = get_article(req['data'], url=req['url'], encoding_in=req['encoding'], encoding_out='unicode')

    if sys.flags.interactive:
        print('>>> Interactive shell: try using `article`')

    else:
        print(article)
