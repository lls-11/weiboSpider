# -*- coding: UTF-8 -*-
"""诺贝尔奖官网：获奖者自传（Biographical）、晚宴致辞、访谈、诺贝尔讲座。

先用官方 API v2.1（https://api.nobelprize.org/2.1/laureates）列出获奖者，
再从 API 返回的 nobelprize.org 链接推出每位获奖者的页面根地址，例如
    https://www.nobelprize.org/prizes/physics/1965/feynman/
并依次抓取 biographical/、speech/、interview/、lecture/。
若 API 链接中没有页面地址，则从该年该奖项的 summary/ 页面里查找。

Biographical 页面多数为获奖时本人撰写的自传（文中有 “This autobiography” 字样），
是覆盖童年至获奖的回顾性发展叙事，最适合做阶段分析。
网站内容版权属于 Nobel Prize Outreach，仅用于研究分析，不要公开再分发原文。
"""

import logging
import re
import unicodedata

from .. import corpus, extract

logger = logging.getLogger('talent_corpus.nobel')

API = 'https://api.nobelprize.org/2.1/laureates'
SITE = 'https://www.nobelprize.org/prizes/'
CATEGORIES = {
    'phy': 'physics', 'che': 'chemistry', 'med': 'medicine',
    'eco': 'economic-sciences', 'lit': 'literature', 'pea': 'peace',
}
PAGE_TYPES = ('biographical', 'speech', 'interview', 'lecture')

_BASE = re.compile(
    r'https?://www\.nobelprize\.org/prizes/([a-z\-]+)/(\d{4})/([a-z0-9\-]+)/')
_NOT_SLUG = {'summary', 'prize-announcement', 'press-release', 'facts',
             'advanced-information', 'popular-information', 'ceremony-speech',
             'award-ceremony-speech', 'nobel-prize-talks'}


def _en(v):
    if isinstance(v, dict):
        return v.get('en') or next(iter(v.values()), '')
    return v or ''


def _ascii(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore') \
        .decode().lower()


def list_laureates(fetcher, categories=('phy', 'che', 'med'), year_from=None,
                   year_to=None, page_size=100):
    """返回 [{laureate_id, name, gender, birth_year, prizes:[...], bases:[...]}]。"""
    out = []
    for cat in categories:
        offset = 0
        while True:
            params = {'offset': offset, 'limit': page_size,
                      'nobelPrizeCategory': cat}
            if year_from:
                params['nobelPrizeYear'] = year_from
                if year_to:
                    params['yearTo'] = year_to
            data = fetcher.get_json(API, params=params)
            for lau in data.get('laureates', []):
                out.append(_laureate_record(lau, cat))
            meta = data.get('meta', {})
            offset += page_size
            if offset >= meta.get('count', 0):
                break
    return out


def _laureate_record(lau, cat):
    name = _en(lau.get('knownName')) or _en(lau.get('orgName')) or \
        _en(lau.get('fullName'))
    birth = (lau.get('birth') or {}).get('date', '')
    prizes, bases = [], []
    hrefs = [ln.get('href', '') for ln in lau.get('links', [])]
    for p in lau.get('nobelPrizes', []):
        prizes.append({'year': p.get('awardYear', ''),
                       'category': _en(p.get('category')),
                       'motivation': _en(p.get('motivation'))})
        hrefs += [ln.get('href', '') for ln in p.get('links', [])]
    for h in hrefs:
        m = _BASE.match(h or '')
        if m and m.group(3) not in _NOT_SLUG:
            b = m.group(0)
            if b not in bases:
                bases.append(b)
    return {'laureate_id': str(lau.get('id', '')), 'name': name,
            'gender': lau.get('gender', ''), 'birth_year': birth[:4],
            'category_code': cat, 'prizes': prizes, 'bases': bases}


def find_bases_from_summary(fetcher, cat, year, name):
    """API 未给出页面地址时，从 summary 页面按姓名匹配获奖者页面。"""
    url = '%s%s/%s/summary/' % (SITE, CATEGORIES[cat], year)
    html_text = fetcher.get(url)
    tree = extract.parse(html_text) if html_text else None
    if tree is None:
        return []
    tokens = [t for t in re.split(r'[^a-z]+', _ascii(name)) if len(t) > 2]
    bases = []
    for href in tree.xpath('//a/@href'):
        m = _BASE.match(href)
        if not m or m.group(3) in _NOT_SLUG:
            continue
        if any(t in m.group(3) for t in tokens) and m.group(0) not in bases:
            bases.append(m.group(0))
    return bases


def narrative_voice(text):
    """按第一人称代词密度区分自传与他人撰写的传记。

    页脚 “This autobiography/biography was written...” 对两类页面相同，不能用来判断。
    """
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 'narrator'
    first = sum(1 for w in words if w in ('I', 'my', 'My', 'me', 'myself'))
    return 'self' if first * 1000 / len(words) >= 8 else 'narrator'


def fetch_laureate_docs(fetcher, lau, page_types=PAGE_TYPES, min_chars=300):
    bases = lau['bases']
    if not bases and lau['prizes']:
        bases = find_bases_from_summary(fetcher, lau['category_code'],
                                        lau['prizes'][0]['year'], lau['name'])
    docs = []
    pid = 'nobel_' + lau['laureate_id']
    for base in bases[:1]:
        m = _BASE.match(base)
        for pt in page_types:
            url = base + pt + '/'
            html_text = fetcher.get(url)
            parsed = extract.extract(html_text, url) if html_text else None
            if not parsed or len(parsed['text']) < min_chars:
                continue
            voice = 'self' if pt in ('speech', 'interview', 'lecture') \
                else narrative_voice(parsed['text'])
            docs.append(corpus.new_doc(
                'nobel', pt, url, parsed['title'], parsed['text'],
                name=lau['name'], pid=pid, laureate_id=lau['laureate_id'],
                category=m.group(1), award_year=m.group(2),
                birth_year=lau['birth_year'], gender=lau['gender'],
                motivation=lau['prizes'][0]['motivation']
                if lau['prizes'] else '',
                narrative_voice=voice, language='en'))
    if not docs:
        logger.info('未找到页面：%s', lau['name'])
    return docs
