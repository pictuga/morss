import lxml.etree
import lxml.html
import re


def parse(data):
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
    'shoutbox', 'sidebar', 'sponsor', 'ad-break', 'agegate', 'pagination',
    'pager', 'popup', 'tweet', 'twitter', 'com-', 'sharing', 'share', 'social',
    'contact', 'footnote', 'masthead', 'media', 'meta', 'outbrain', 'promo',
    'related', 'scroll', 'shoutbox', 'sidebar', 'sponsor', 'shopping', 'tags',
    'tool', 'widget']), re.I)

regex_good = re.compile('|'.join(['and', 'article', 'body', 'column',
    'main', 'shadow', 'content', 'entry', 'hentry', 'main', 'page',
    'pagination', 'post', 'text', 'blog', 'story', 'par']), re.I)

tags_junk = ['script', 'head', 'iframe', 'object', 'noscript', 'param', 'embed', 'layer', 'applet', 'style']

attributes_fine = ['title', 'src', 'href', 'type', 'name', 'for', 'value']


def score_node(node):
    score = 0

    if node.tag in tags_junk:
        return 0

    if isinstance(node, lxml.html.HtmlComment):
        return 0

    if node.tag in ['a']:
        score -= 1

    if node.tag in ['h1', 'h2', 'article']:
        score += 8

    if node.tag in ['p']:
        score += 3

    class_id = node.get('class', '') + node.get('id', '')

    score += len(regex_good.findall(class_id) * 4)
    score -= len(regex_bad.findall(class_id) * 3)

    score += count_words(''.join([node.text or ''] + [x.tail or '' for x in node])) / 10. # the .tail part is to include *everything* in that node

    return score


def score_all(root):
    grades = {}

    for item in root.iter():
        score = score_node(item)

        grades[item] = score

        parent = item.getparent()
        if parent is not None:
            grades[parent] += score / 2.

            gdparent = parent.getparent()
            if gdparent is not None:
                grades[gdparent] += score / 4.

    return grades


def get_best_node(root):
    return sorted(score_all(root).items(), key=lambda x: x[1], reverse=True)[0][0]


def clean_html(root):
    for item in root.iter():
        # Step 1. Do we keep the node?

        if item.tag in tags_junk:
            item.getparent().remove(item)

        class_id = item.get('class', '') + item.get('id', '')
        if regex_bad.match(class_id):
            item.getparent().remove(item)

        if isinstance(item, lxml.html.HtmlComment):
            item.getparent().remove(item)

        # Step 2. Clean the node's attributes

        for attrib in item.attrib:
            if attrib not in attributes_fine:
                del item.attrib[attrib]


def br2p(root):
    for item in root.iterfind('.//br'):
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


def get_article(data):
    return lxml.etree.tostring(get_best_node(parse(data)))
