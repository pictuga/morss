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

    for node in list(root.iter()):
        score = score_node(node)

        parent = node.getparent()
        clean_node(node)

        if parent is not None and node.getparent() is None:
            # if the node got deleted/dropped (else, nothing to do)
            # maybe now the parent only contains 1 item and needs to be flattened?

            gdparent = parent.getparent()
            clean_node(parent)

            if gdparent is not None and parent.getparent() is None:
                # if the parent got deleted/dropped
                spread_score(gdparent, score + grades[parent], grades)

            else:
                # if the parent was kept
                spread_score(parent, score, grades)

        else:
            # if the node was kept
            spread_score(node, score, grades)

    return grades


def spread_score(node, score, grades):
    " Spread the node's score to its parents, on a linear way "

    delta = score / 2
    for ancestor in [node,] + list(node.iterancestors()):
        if score >= 1 or ancestor is node:
            try:
                grades[ancestor] += score
            except KeyError:
                grades[ancestor] = score

            score -= delta

        else:
            break


def write_score_all(root, grades):
    for node in root.iter():
        node.attrib['score'] = str(int(grades.get(node, 0)))


def clean_node(node):
    # Step 1. Do we keep the node?

    if node.getparent() is None:
        # this is <html/>
        return

    if node.tag in tags_junk:
        # remove shitty tags
        node.getparent().remove(node)
        return

    # Turn <div><p>Bla bla bla</p></div> into <p>Bla bla bla</p>

    if node.tag in ['div'] \
        and len(list(node.iterchildren())) <= 1 \
        and not (node.text or '').strip() \
        and not (node.tail or '').strip():
        node.drop_tag()
        return

    class_id = node.get('class', '') + node.get('id', '')
    if len(regex_junk.findall(class_id)) >= 2:
        # remove shitty class/id
        node.getparent().remove(node)
        return

    if node.tag == 'a' and len(list(node.iter())) > 3:
        # shitty link
        node.getparent().remove(node)
        return

    if isinstance(node, lxml.html.HtmlComment):
        # remove comments
        node.getparent().remove(node)
        return

    # Step 2. Clean the node's attributes

    for attrib in node.attrib:
        if attrib not in attributes_fine:
            del node.attrib[attrib]


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


def get_best_node(grades):
    " To pick the best (raw) node. Another function will clean it "

    if len(grades) == 1:
        return grades[0]

    top = rank_nodes(grades)
    lowest = lowest_common_ancestor(top[0][0], top[1][0], 3)

    return lowest


def get_article(data, url=None, encoding=None):
    html = parse(data, encoding)
    br2p(html)
    scores = score_all(html)

    if not len(scores):
        return None

    best = get_best_node(scores)
    wc = count_words(best.text_content())
    wca = count_words(' '.join([x.text_content() for x in best.findall('.//a')]))

    if wc - wca < 50 or float(wca) / wc > 0.3:
        return None

    if url:
        best.make_links_absolute(url)

    return lxml.etree.tostring(best)
