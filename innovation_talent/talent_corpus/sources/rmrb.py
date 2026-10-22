# -*- coding: UTF-8 -*-
"""《人民日报》电子版：抓取五四前后刊登的国家奖学金获奖学生代表名录。

电子版有两种地址格式（均已在公开检索结果中核对）：
    新版  https://paper.people.com.cn/rmrb/pc/layout/202605/04/node_05.html
          https://paper.people.com.cn/rmrb/pc/content/202605/04/content_30154802.html
    旧版  https://paper.people.com.cn/rmrb/html/2024-05/04/nbs.D110000renmrb_06.htm
          https://paper.people.com.cn/rmrb/html/2024-05/04/nw.D110000renmrb_20240504_1-06.htm
2024 年 12 月 1 日起为新版；程序按日期先试对应格式，再试另一种。

名录条目的排版各年可能不同。parse_entries 先用“段首加粗姓名”识别条目，
再用“姓名 + 院校名”的正则兜底；每年首次运行后请用 --dump-raw 输出的原文核对条目数。
"""

import logging
import re
from datetime import date, timedelta
from urllib.parse import urljoin

from .. import corpus, extract

logger = logging.getLogger('talent_corpus.rmrb')

BASE = 'https://paper.people.com.cn/rmrb/'
DEFAULT_KEYWORDS = ('国家奖学金', '获奖学生代表')

_NEW_PAGE = re.compile(r'node_(\d+)\.html')
_NEW_ART = re.compile(r'content_\d+\.html')
_OLD_PAGE = re.compile(r'nbs\.D110000renmrb_(\d+)\.htm')
_OLD_ART = re.compile(r'nw\.D110000renmrb_\d{8}_\d+-\d+\.htm')

_HAN_NAME = r'[一-龥][一-龥·]{1,5}'
_INSTITUTION = re.compile(
    r'[一-龥A-Za-z（）()]{2,30}?'
    r'(大学|学院|学校|研究院|研究所|科学院|研究中心|党校)')
_HEADER = re.compile(r'^(' + _HAN_NAME + r')[\s，,：:、|｜]+(.{0,80})$')
_PROGRAM = re.compile(
    r'((?:19|20)\d{2}级)?[^，。；,;]{0,20}?'
    r'(本科生|专科生|高职生|硕士研究生|博士研究生|硕士生|博士生|研究生|直博生)')
_NOT_NAMES = {'此外', '同时', '其中', '目前', '近年', '近年来', '此前', '随后',
              '后来', '如今', '当时', '期间', '因此', '截至', '另外', '在校',
              '本科', '硕士', '博士', '读研', '读博', '大学', '学校', '学院'}
_NOT_NAME_START = ('他', '她', '在', '从', '作', '曾', '以', '为', '将', '把',
                   '于', '自', '和', '与', '先', '并', '共', '全')


# 2024-12-01 起使用新版地址（与 github.com/AnzhiZhang/PeoplesDaily 的判断一致）
NEW_FORMAT_FROM = date(2024, 12, 1)


def page_one_urls(d):
    """返回 [(格式, 第 1 版地址)]：按日期把更可能的格式放在前面，另一种作为后备。"""
    urls = [
        ('new', BASE + 'pc/layout/%s/%s/node_01.html' %
         (d.strftime('%Y%m'), d.strftime('%d'))),
        ('old', BASE + 'html/%s/%s/nbs.D110000renmrb_01.htm' %
         (d.strftime('%Y-%m'), d.strftime('%d'))),
    ]
    return urls if d >= NEW_FORMAT_FROM else urls[::-1]


_DAY = re.compile(r'/(\d{6}/\d{2}|\d{4}-\d{2}/\d{2})/')


def _same_day(url, base_url):
    """版面里有“上一期”“下一期”等指向其他日期的链接，只保留同一天的地址。"""
    a, b = _DAY.search(url), _DAY.search(base_url)
    return bool(a and b) and a.group(1) == b.group(1)


def page_urls(html_text, base_url, fmt):
    pat = _NEW_PAGE if fmt == 'new' else _OLD_PAGE
    tree = extract.parse(html_text)
    found = {}
    if tree is not None:
        for href in tree.xpath('//a/@href'):
            m = pat.search(href)
            u = urljoin(base_url, href)
            if m and _same_day(u, base_url):
                found[int(m.group(1))] = u
    found[1] = base_url
    return [found[k] for k in sorted(found)]


def article_links(html_text, base_url, fmt):
    """返回 [(文章地址, 链接文字)]，同一地址的多个链接文字合并。"""
    pat = _NEW_ART if fmt == 'new' else _OLD_ART
    tree = extract.parse(html_text)
    links = {}
    if tree is not None:
        for a in tree.xpath('//a[@href]'):
            href = a.get('href')
            u = urljoin(base_url, href)
            if pat.search(href) and _same_day(u, base_url):
                text = extract.normalize(a.text_content()).replace('\n', ' ')
                links[u] = (links.get(u, '') + ' ' + text).strip()
    return list(links.items())


def article_urls(html_text, base_url, fmt):
    return [u for u, _ in article_links(html_text, base_url, fmt)]


def article_paragraphs(html_text):
    """返回 [(段落文本, 段首加粗文本)]。"""
    tree = extract.parse(html_text)
    if tree is None:
        return []
    nodes = tree.xpath('//*[@id="ozoom"]')
    root = nodes[0] if nodes else tree
    out = []
    for p in root.xpath('.//p'):
        text = extract.normalize(p.text_content()).replace('\n', ' ')
        if not text:
            continue
        lead = ''
        bold = p.xpath('.//strong|.//b')
        if bold:
            b = extract.normalize(bold[0].text_content()).replace('\n', ' ')
            if b and text.startswith(b):
                lead = b
        out.append((text, lead))
    return out


def _is_name(s):
    s = s.strip()
    return (2 <= len(s) <= 6 and re.fullmatch(_HAN_NAME, s) is not None
            and s not in _NOT_NAMES and not s.startswith(_NOT_NAME_START))


def _header(text, lead):
    """判断段落是否为条目开头，返回 (姓名, 段内其余文本, 识别方式) 或 None。"""
    if lead and _is_name(lead):
        return lead, text[len(lead):].lstrip(' ，,：:、|｜'), 'bold'
    m = _HEADER.match(text)
    if m and _is_name(m.group(1)) and _INSTITUTION.search(m.group(2)[:40]):
        return m.group(1), m.group(2), 'regex'
    if _is_name(text):
        return text, '', 'name_only'
    return None


def parse_entries(paragraphs):
    """把名录正文切分为学生条目。段首识别失败的段落并入上一条目。"""
    entries, cur = [], None
    for text, lead in paragraphs:
        h = _header(text, lead)
        if h:
            if cur:
                entries.append(cur)
            name, rest, how = h
            cur = {'name': name, 'lines': [rest] if rest else [], 'how': how}
        elif cur:
            cur['lines'].append(text)
    if cur:
        entries.append(cur)
    out = []
    for e in entries:
        body = '\n'.join(e['lines']).strip()
        head = body[:80]
        inst = _INSTITUTION.search(head)
        prog = _PROGRAM.search(head)
        out.append({
            'name': e['name'],
            'school': inst.group(0) if inst else '',
            'program': prog.group(0) if prog else '',
            'text': body,
            'parse_method': e['how'],
        })
    # 只有姓名、没有内容的条目通常是误判（如小标题）
    return [e for e in out if e['text'] or e['parse_method'] != 'name_only']


def list_level(title):
    if '研究生' in title:
        return 'graduate'
    if '中等职业' in title or '中职' in title:
        return 'vocational'
    if '本专科' in title or '本科' in title:
        return 'undergraduate'
    return ''


def award_year(title):
    m = re.search(r'((?:19|20)\d{2})\s*[—–-]+\s*((?:19|20)\d{2})\s*学年', title)
    if m:
        return m.group(1) + '-' + m.group(2)
    m = re.search(r'((?:19|20)\d{2})\s*年', title)
    return m.group(1) if m else ''


def crawl_date(fetcher, d, keywords=DEFAULT_KEYWORDS, scan_all=False):
    """抓取某一天的电子版，返回标题或正文含关键词的文章。

    默认只打开版面目录中标题含关键词的文章（每天约 20 个版面 + 几篇文章）；
    scan_all=True 时打开全部文章再判断，慢很多，用于标题不含关键词的年份。
    """
    for fmt, first in page_one_urls(d):
        html_text = fetcher.get(first)
        # 某些不存在的版面会返回 200 的提示页，以能否找到当天的文章链接为准
        if html_text and article_urls(html_text, first, fmt):
            break
    else:
        logger.info('%s 无电子版或无法访问', d)
        return []
    pages = page_urls(html_text, first, fmt)
    logger.info('%s 共 %d 个版面（%s版地址）', d, len(pages),
                '新' if fmt == 'new' else '旧')
    articles = []
    for i, purl in enumerate(pages):
        page_html = html_text if i == 0 else fetcher.get(purl)
        if not page_html:
            continue
        for aurl, link_text in article_links(page_html, purl, fmt):
            if not scan_all and not any(k in link_text for k in keywords):
                continue
            ahtml = fetcher.get(aurl)
            if not ahtml:
                continue
            parsed = extract.extract(ahtml, aurl) or {}
            title = parsed.get('title', '')
            text = parsed.get('text', '')
            if not any(k in title or k in text[:300] for k in keywords):
                continue
            logger.info('  第 %d 版：%s', i + 1, title)
            articles.append({
                'date': d.isoformat(), 'page': i + 1, 'url': aurl,
                'format': fmt, 'title': title, 'text': text,
                'paragraphs': article_paragraphs(ahtml),
            })
    if not articles:
        logger.info('%s 未找到名录', d)
    return articles


def to_docs(article, include_vocational=False):
    level = list_level(article['title'])
    if level == 'vocational' and not include_vocational:
        return []
    year = award_year(article['title'])
    docs = []
    for e in parse_entries(article['paragraphs']):
        docs.append(corpus.new_doc(
            'rmrb_scholarship', 'list_entry', article['url'],
            article['title'], e['text'], name=e['name'],
            school=e['school'], program=e['program'], level=level,
            award_year=year, publish_date=article['date'],
            page=article['page'], parse_method=e['parse_method']))
    return docs


def check_counts(docs, expected=100, tolerance=15):
    """每份名录（日期 × 层次）应约有 100 条，偏离较大时提示人工核对。"""
    counts = {}
    for d in docs:
        key = (d['publish_date'], d['level'])
        counts[key] = counts.get(key, 0) + 1
    for (day, level), n in sorted(counts.items()):
        if abs(n - expected) > tolerance:
            logger.warning('%s %s 名录解析出 %d 条（预期约 %d 条），'
                           '请用 --dump-raw 输出的原文核对条目切分。',
                           day, level, n, expected)
    return counts


def dates_for(years, window=('05-03', '05-06')):
    out = []
    for y in years:
        start = date(y, *map(int, window[0].split('-')))
        end = date(y, *map(int, window[1].split('-')))
        d = start
        while d <= end:
            out.append(d)
            d += timedelta(days=1)
    return out
