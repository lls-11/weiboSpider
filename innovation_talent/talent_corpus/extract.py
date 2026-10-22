# -*- coding: UTF-8 -*-
"""网页正文抽取：微信公众号文章、高校新闻网常见内容管理系统、通用密度兜底。"""

import re

from lxml import etree, html as lhtml

BLOCK_TAGS = {'p', 'div', 'section', 'br', 'li', 'h1', 'h2', 'h3', 'h4',
              'h5', 'h6', 'tr', 'blockquote', 'table'}
DROP_TAGS = ('script', 'style', 'noscript', 'iframe', 'svg', 'form',
             'button', 'select', 'textarea')

# 依次尝试的正文容器（XPath），覆盖人民日报电子版与高校网站常见系统
CONTENT_XPATHS = [
    ('rmrb', '//*[@id="ozoom"]'),
    ('wechat', '//*[@id="js_content"]'),
    ('visualsitebuilder', '//*[contains(@class,"v_news_content")]'),
    ('visualsitebuilder', '//*[@id="vsb_content"]'),
    ('webplus', '//*[contains(@class,"wp_articlecontent")]'),
    ('trs', '//*[contains(@class,"TRS_Editor")]'),
    ('generic', '//*[contains(@class,"article-content")]'),
    ('generic', '//*[contains(@class,"article_content")]'),
    ('generic', '//*[contains(@class,"news_content")]'),
    ('generic', '//*[contains(@class,"news-content")]'),
    ('generic', '//*[@id="content"]'),
    ('generic', '//article'),
]

WECHAT_BLOCKED = ('环境异常', '完成验证后即可继续访问', '该内容已被发布者删除',
                  '此内容因违规无法查看', '该公众号已迁移')

_DATE = re.compile(
    r'((?:19|20)\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?')
_SPACES = re.compile(r'[ \t 　  ​]+')


def normalize(text):
    lines = []
    for line in text.splitlines():
        line = _SPACES.sub(' ', line).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def element_text(el):
    """把元素转为纯文本，块级元素之间换行。"""
    el = _clean(el)
    parts = []

    def walk(node):
        if not isinstance(node.tag, str):
            if node.tail:
                parts.append(node.tail)
            return
        tag = node.tag.lower()
        if tag in BLOCK_TAGS:
            parts.append('\n')
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if tag in BLOCK_TAGS:
            parts.append('\n')
        if node.tail:
            parts.append(node.tail)

    if el.text:
        parts.append(el.text)
    for child in el:
        walk(child)
    return normalize(''.join(parts))


def _clean(el):
    el = lhtml.fromstring(etree.tostring(el, encoding='unicode'))
    for bad in el.xpath('|'.join('.//' + t for t in DROP_TAGS)):
        bad.drop_tree()
    for c in el.xpath('.//comment()'):
        c.drop_tree()
    return el


def parse(html_text):
    if not html_text or not html_text.strip():
        return None
    try:
        return lhtml.fromstring(html_text)
    except (etree.ParserError, ValueError):
        return None


def find_title(tree):
    for xp in ('//*[@id="activity-name"]', '//h1', '//h2',
               '//meta[@property="og:title"]/@content', '//title'):
        r = tree.xpath(xp)
        if r:
            t = r[0] if isinstance(r[0], str) else r[0].text_content()
            t = normalize(t).replace('\n', ' ')
            if t:
                return t
    return ''


def find_date(tree, html_text):
    for xp in ('//meta[@name="publishdate"]/@content',
               '//meta[@name="PubDate"]/@content',
               '//meta[@property="article:published_time"]/@content',
               '//*[@id="publish_time"]/text()'):
        r = tree.xpath(xp)
        if r:
            m = _DATE.search(r[0])
            if m:
                return '%s-%02d-%02d' % (m.group(1), int(m.group(2)),
                                         int(m.group(3)))
    m = re.search(r'var\s+ct\s*=\s*"(\d{10})"', html_text)
    if m:
        from datetime import datetime
        return datetime.fromtimestamp(int(m.group(1))).strftime('%Y-%m-%d')
    m = re.search(r'(发布时间|发布日期|时间)[:：\s]*' + _DATE.pattern, html_text)
    if m:
        return '%s-%02d-%02d' % (m.group(2), int(m.group(3)), int(m.group(4)))
    return ''


def _density_fallback(tree):
    """选出直接包含最多段落文字的容器。"""
    best, best_len = None, 0
    for node in tree.xpath('//div|//section|//td|//article'):
        n = sum(len(p.text_content().strip()) for p in node.xpath('./p'))
        if n > best_len:
            best, best_len = node, n
    return best


def extract(html_text, url=''):
    """返回 {title, text, publish_time, extractor, blocked}；无法解析时返回 None。"""
    tree = parse(html_text)
    if tree is None:
        return None
    is_wechat = 'mp.weixin.qq.com' in url or 'js_content' in html_text
    if is_wechat and any(k in html_text for k in WECHAT_BLOCKED) and \
            not tree.xpath('//*[@id="js_content"]'):
        return {'title': '', 'text': '', 'publish_time': '',
                'extractor': 'wechat', 'blocked': True}
    body, name = None, 'density'
    for label, xp in CONTENT_XPATHS:
        for node in tree.xpath(xp):
            if len(node.text_content().strip()) >= 40:
                body, name = node, label
                break
        if body is not None:
            break
    if body is None:
        body = _density_fallback(tree)
    if body is None:
        return None
    return {
        'title': find_title(tree),
        'text': element_text(body),
        'publish_time': find_date(tree, html_text),
        'extractor': name,
        'blocked': False,
    }
