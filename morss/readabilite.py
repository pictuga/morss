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


regex_bad = re.compile('|'.join(['comment', 'community', 'extra', 'foot',
    'sponsor', 'pagination', 'pager', 'tweet', 'twitter', 'com-', 'masthead',
    'media', 'meta', 'related', 'shopping', 'tags', 'tool', 'author', 'about']),
    re.I)

regex_junk = re.compile('|'.join(['robots-nocontent', 'combx', 'disqus',
    'header', 'menu', 'remark', 'rss', 'shoutbox', 'sidebar', 'ad-', 'agegate',
    'popup', 'sharing', 'share', 'social', 'contact', 'footnote', 'outbrain',
    'promo', 'scroll', 'hidden', 'widget', 'hide']), re.I)

regex_good = re.compile('|'.join(['and', 'article', 'body', 'column', 'main',
    'shadow', 'content', 'entry', 'hentry', 'main', 'page', 'pagination',
    'post', 'text', 'blog', 'story', 'par', 'editorial']), re.I)


tags_bad = ['a']

tags_junk = ['script', 'head', 'iframe', 'object', 'noscript', 'param', 'embed',
    'layer', 'applet', 'style', 'form', 'input', 'textarea', 'button', 'footer']

tags_good = ['h1', 'h2', 'h3', 'article', 'p', 'cite', 'section', 'img',
    'figcaption', 'figure']


attributes_fine = ['title', 'src', 'href', 'type', 'name', 'for', 'value']


def score_node(node):
    score = 0

    if isinstance(node, lxml.html.HtmlComment):
        return 0

    class_id = node.get('class', '') + node.get('id', '')

    score -= len(regex_bad.findall(class_id))
    score -= len(regex_junk.findall(class_id))
    score += len(regex_good.findall(class_id))

    wc = count_words(''.join([node.text or ''] + [x.tail or '' for x in node]))
    # the .tail part is to include *everything* in that node

    if wc > 10:
        score += 1

    if wc > 20:
        score += 1

    if wc > 30:
        score += 1

    if node.tag in tags_bad or node.tag in tags_junk:
        score = -1 * abs(score)

    if node.tag in tags_good:
        score += 3

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
    for node in root.iter():
        node.attrib['score'] = str(int(grades[node]))


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
    for node in list(root.iterfind('.//br')):
        parent = node.getparent()
        if parent is None:
            continue

        gdparent = parent.getparent()
        if gdparent is None:
            continue

        if node.tail is None:
            # if <br/> is at the end of a div (to avoid having <p/>)
            continue

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


def rank_nodes(grades):
    return sorted(grades.items(), key=lambda x: x[1], reverse=True)


def get_best_node(grades, highlight=False):
    top = rank_nodes(grades)
    lowest = lowest_common_ancestor(top[0][0], top[1][0], 3)

    if highlight:
        top[0][0].attrib['style'] = 'border: 2px solid blue'
        top[1][0].attrib['style'] = 'border: 2px solid green'
        lowest.attrib['style'] = 'outline: 2px solid red'

    return lowest


def get_article(data, url=None, encoding=None):
    html = parse(data, encoding)

    clean_html(html)
    br2p(html)

    scores = score_all(html)
    best = get_best_node(scores)

    if url:
        best.make_links_absolute(url)

    return lxml.etree.tostring(best)
