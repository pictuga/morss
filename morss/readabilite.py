import lxml.etree
import lxml.html
from bs4 import BeautifulSoup
import re


def parse(data, encoding=None):
    if encoding:
        parser = lxml.html.HTMLParser(remove_blank_text=True, remove_comments=True, encoding=encoding)
    else:
        parser = lxml.html.HTMLParser(remove_blank_text=True, remove_comments=True)

    return lxml.html.fromstring(BeautifulSoup(data, 'lxml').prettify('utf-8'), parser=parser)


def count_words(string):
    """ Quick word count

    Simply assumes that all words are 5 letter long.
    And so in about every language (sorry chinese).
    Basically skips spaces in the count. """

    if string is None:
        return 0

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


def percentile(N, P):
    # https://stackoverflow.com/a/7464107
    n = max(int(round(P * len(N) + 0.5)), 2)
    return N[n-2]


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


tags_junk = ['script', 'head', 'iframe', 'object', 'noscript',
    'param', 'embed', 'layer', 'applet', 'style', 'form', 'input', 'textarea',
    'button', 'footer', 'link', 'meta']

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
    class_id = node.get('class', '') + node.get('id', '')

    if (isinstance(node, lxml.html.HtmlComment)
            or isinstance(node, lxml.html.HtmlProcessingInstruction)):
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
        score = score * ( 1 - float(wca)/wc )

    return score


def score_all(node):
    " Fairly dumb loop to score all worthwhile nodes. Tries to be fast "

    for child in node:
        score = score_node(child)
        child.attrib['seen'] = 'yes, ' + str(int(score))

        if score > 0 or len(list(child.iterancestors())) <= 2:
            spread_score(child, score)
            score_all(child)


def set_score(node, value):
    node.attrib['morss_score'] = str(float(value))


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

    if parent is None:
        # this is <html/> (or a removed element waiting for GC)
        return

    if keep_threshold is not None and get_score(node) >= keep_threshold:
        # high score, so keep
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

    # remove comments
    if isinstance(node, lxml.html.HtmlComment) or isinstance(node, lxml.html.HtmlProcessingInstruction):
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


def lowest_common_ancestor(nodeA, nodeB, max_depth=None):
    ancestorsA = list(nodeA.iterancestors())
    ancestorsB = list(nodeB.iterancestors())

    if max_depth is not None:
        ancestorsA = ancestorsA[:max_depth]
        ancestorsB = ancestorsB[:max_depth]

    ancestorsA.insert(0, nodeA)
    ancestorsB.insert(0, nodeB)

    for ancestorA in ancestorsA:
        if ancestorA in ancestorsB:
            return ancestorA

    return nodeA # should always find one tho, at least <html/>, but needed for max_depth


def rank_grades(grades):
    # largest score to smallest
    return sorted(grades.items(), key=lambda x: x[1], reverse=True)


def get_best_node(ranked_grades):
    " To pick the best (raw) node. Another function will clean it "

    if len(ranked_grades) == 1:
        return ranked_grades[0]

    lowest = lowest_common_ancestor(ranked_grades[0][0], ranked_grades[1][0], 3)

    return lowest


def get_article(data, url=None, encoding=None):
    " Input a raw html string, returns a raw html string of the article "

    html = parse(data, encoding)
    score_all(html)
    scores = rank_grades(get_all_scores(html))

    if not len(scores):
        return None

    best = get_best_node(scores)
    wc = count_words(best.text_content())
    wca = count_words(' '.join([x.text_content() for x in best.findall('.//a')]))

    if wc - wca < 50 or float(wca) / wc > 0.3:
        return None

    if url:
        best.make_links_absolute(url)

    keep_threshold = percentile([x[1] for x in scores], 0.1)
    clean_root(best, keep_threshold)

    return lxml.etree.tostring(best, pretty_print=True)
