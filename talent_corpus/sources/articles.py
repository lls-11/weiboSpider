# -*- coding: UTF-8 -*-
"""高校新闻网、微信公众号等单篇文章的采集。

两种输入：
1. URL 清单（CSV），列：url, name, school, corpus, source_type, person_id, note
   name/school 用于把文章关联到名录中的人物；person_id 可留空，
   留空时按 name + school 生成，与名录条目的 person_id 一致。
2. 本地 HTML 目录：在浏览器里“另存为网页”的文件。微信公众号文章常有访问验证，
   人工保存后用这种方式解析更可靠。同目录下可放一个 index.csv（列：file, url, name, school, ...）。

make_search_sheet 根据名录生成检索工作表：每人一行，附百度、必应、搜狗微信的检索链接，
由研究助理检索并把找到的文章地址填入 url 列，再交给 fetch_url_list。
"""

import csv
import logging
import os
from urllib.parse import quote

from .. import corpus, extract
from ..fetch import decode_html

logger = logging.getLogger('talent_corpus.articles')

SHEET_FIELDS = ['url', 'name', 'school', 'corpus', 'source_type', 'person_id',
                'note']


def _source_type(url, default='news'):
    return 'wechat' if 'mp.weixin.qq.com' in url else default


def read_url_list(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f) if (r.get('url') or '').strip()]


def _to_doc(row, parsed, url):
    name = (row.get('name') or '').strip()
    school = (row.get('school') or '').strip()
    return corpus.new_doc(
        (row.get('corpus') or 'univ_article').strip(),
        (row.get('source_type') or _source_type(url)).strip(),
        url, parsed['title'], parsed['text'], name=name,
        pid=(row.get('person_id') or '').strip() or None, school=school,
        publish_time=parsed['publish_time'], extractor=parsed['extractor'],
        note=row.get('note', ''))


def fetch_url_list(fetcher, rows, min_chars=150):
    docs, failed = [], []
    for row in rows:
        url = row['url'].strip()
        html_text = fetcher.get(url)
        parsed = extract.extract(html_text, url) if html_text else None
        if not parsed or parsed.get('blocked'):
            reason = 'blocked' if parsed else 'no_content'
            failed.append(dict(row, reason=reason))
            continue
        if len(parsed['text']) < min_chars:
            failed.append(dict(row, reason='too_short'))
            continue
        docs.append(_to_doc(row, parsed, url))
    return docs, failed


def parse_local_dir(path, min_chars=150):
    """解析浏览器保存的网页；index.csv 可选。"""
    index = {}
    idx_path = os.path.join(path, 'index.csv')
    if os.path.exists(idx_path):
        with open(idx_path, encoding='utf-8-sig', newline='') as f:
            index = {r['file']: r for r in csv.DictReader(f)}
    docs, failed = [], []
    for fn in sorted(os.listdir(path)):
        if not fn.lower().endswith(('.html', '.htm')):
            continue
        with open(os.path.join(path, fn), 'rb') as f:
            html_text = decode_html(f.read())
        row = index.get(fn, {})
        url = row.get('url') or 'file://' + fn
        parsed = extract.extract(html_text, url)
        if not parsed or parsed.get('blocked') or \
                len(parsed['text']) < min_chars:
            failed.append({'file': fn, 'reason': 'no_content'})
            continue
        docs.append(_to_doc(row, parsed, url))
    return docs, failed


def make_search_sheet(entries, path):
    """为每位人物生成检索链接，写成 CSV 工作表。"""
    rows = []
    for e in entries:
        name, school = e.get('name', ''), e.get('school', '')
        q1 = '"%s" %s 国家奖学金' % (name, school)
        q2 = '"%s" site:edu.cn' % name
        rows.append({
            'url': '', 'name': name, 'school': school,
            'corpus': 'univ_article', 'source_type': '',
            'person_id': e.get('person_id', ''),
            'note': '',
            'level': e.get('level', ''),
            'award_year': e.get('award_year', ''),
            'baidu': 'https://www.baidu.com/s?wd=' + quote(q1),
            'bing': 'https://cn.bing.com/search?q=' + quote(q1),
            'bing_edu': 'https://cn.bing.com/search?q=' + quote(q2),
            'sogou_wechat': 'https://weixin.sogou.com/weixin?type=2&query=' +
            quote('%s %s' % (name, school)),
        })
    fields = SHEET_FIELDS + ['level', 'award_year', 'baidu', 'bing',
                             'bing_edu', 'sogou_wechat']
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return len(rows)
