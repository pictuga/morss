import lxml.etree
import lxml.html
import re


def parse(data, encoding=None):
    if encoding:
        parser = lxml.html.HTMLParser(remove_blank_text=True, remove_comments=True, encoding=encoding)
    else:
        parser = lxml.html.HTMLParser(remove_blank_text=True, remove_comments=True)

    return lxml.html.fromstring(data, parser=parser)


def count_words(string):
    """ Quick word count

    Simply assumes that all words are 5 letter long.
    And so in about every language (sorry chinese).
    Basically skips spaces in the count. """

    i = 0
    count = 0

    try:
        while True:
            if string[i] not in '\n\t ':
                count += 1
                i += 6
            else:
                i += 1
    except IndexError:
        pass

    return count


regex_bad = re.compile('|'.join(['robots-nocontent', 'combx', 'comment',
    'community', 'disqus', 'extra', 'foot', 'header', 'menu', 'remark', 'rss',
    'shoutbox', 'sidebar', 'sponsor', 'ad-', 'agegate', 'pagination',
    'pager', 'popup', 'tweet', 'twitter', 'com-', 'sharing', 'share', 'social',
    'contact', 'footnote', 'masthead', 'media', 'meta', 'outbrain', 'promo',
    'related', 'scroll', 'shoutbox', 'shopping', 'tags',
    'tool', 'widget', 'hide', 'author', 'about']), re.I)

regex_good = re.compile('|'.join(['and', 'article', 'body', 'column',
    'main', 'shadow', 'content', 'entry', 'hentry', 'main', 'page',
    'pagination', 'post', 'text', 'blog', 'story', 'par', 'editorial']), re.I)

tags_junk = ['script', 'head', 'iframe', 'object', 'noscript', 'param', 'embed', 'layer', 'applet', 'style', 'form', 'input', 'textarea', 'button']

attributes_fine = ['title', 'src', 'href', 'type', 'name', 'for', 'value']


def score_node(node):
    score = 0

    if isinstance(node, lxml.html.HtmlComment):
        return 0

    wc = count_words(''.join([node.text or ''] + [x.tail or '' for x in node]))
    # the .tail part is to include *everything* in that node

    if wc < 5:
        return 0

    if node.tag in ['h1', 'h2', 'h3', 'article']:
        score += 8

    if node.tag in ['p', 'cite', 'section']:
        score += 3

    class_id = node.get('class', '') + node.get('id', '')

    score += len(regex_good.findall(class_id) * 5)
    score -= len(regex_bad.findall(class_id) * 3)

    score += wc / 5.

    if node.tag in tags_junk or node.tag in ['a']:
        score *= -1

    return score


def score_all(root):
    grades = {}

    for item in root.iter():
        score = score_node(item)

        grades[item] = score

        factor = 2
        for ancestor in item.iterancestors():
            if score / factor > 1:
                grades[ancestor] += score / factor
                factor *= 2
            else:
                break

    return grades


def write_score_all(root, grades):
    for item in root.iter():
        item.attrib['score'] = str(int(grades[item]))


def clean_html(root):
    for item in list(root.iter()): # list() needed to be able to remove elements while iterating
        # Step 1. Do we keep the node?

        if item.tag in tags_junk:
            # remove shitty tags
            item.getparent().remove(item)
            continue

        if item.tag in ['div'] \
            and len(list(item.iterchildren())) <= 1 \
            and not (item.text or '').strip() \
            and not (item.tail or '').strip():
            # remove div with only one item inside
            item.drop_tag()
            continue

        class_id = item.get('class', '') + item.get('id', '')
        if regex_bad.match(class_id) is not None:
            # remove shitty class/id
            item.getparent().remove(item)
            continue

        if isinstance(item, lxml.html.HtmlComment):
            # remove comments
            item.getparent().remove(item)
            continue

        # Step 2. Clean the node's attributes

        for attrib in item.attrib:
            if attrib not in attributes_fine:
                del item.attrib[attrib]


def br2p(root):
    for item in list(root.iterfind('.//br')):
        parent = item.getparent()
        if parent is None:
            continue

        gdparent = parent.getparent()
        if gdparent is None:
            continue

        if item.tail is None:
            # if <br/> is at the end of a div (to avoid having <p/>)
            continue

        else:
            # set up new item
            new_item = lxml.html.Element(parent.tag)
            new_item.text = item.tail

            for child in item.itersiblings():
                new_item.append(child)

            # delete br
            item.tail = None
            parent.remove(item)

            gdparent.insert(gdparent.index(parent)+1, new_item)


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

    return nodeA # should always find one tho, at least <html/>


def rank_nodes(grades):
    return sorted(grades.items(), key=lambda x: x[1], reverse=True)


def get_best_node(grades):
    top = rank_nodes(grades)

    if top[0][1] < top[1][1] * 1.6:
        # we might still want to include the 2nd best node (great for articles split with images)

        cmn_ancestor = lowest_common_ancestor(top[0][0], top[1][0], 3)
        return cmn_ancestor

    else:
        return top[0][0]


def get_article(data, url=None, encoding=None):
    html = parse(data, encoding)

    clean_html(html)
    br2p(html)

    scores = score_all(html)
    best = get_best_node(scores)

    if url:
        best.make_links_absolute(url)

    return lxml.etree.tostring(best)
