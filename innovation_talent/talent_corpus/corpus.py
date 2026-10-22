# -*- coding: UTF-8 -*-
"""语料记录与 JSONL 读写。

每条文档是一个 dict，必备字段：
    doc_id       文档唯一编号（来源 + 哈希）
    person_id    人物编号（同一人物的多篇文档共享）
    name         人物姓名
    corpus       语料组：rmrb_scholarship / univ_article / nobel / weibo / ...
    source_type  文本类型：list_entry / news / wechat / biographical / speech / interview / lecture / weibo
    url          来源地址（本地文件为 file://）
    title        标题
    text         正文（纯文本，段落以换行分隔）
其余字段（school、level、year、publish_time、category 等）按来源补充。
"""

import hashlib
import json
import os
from datetime import datetime


def make_id(*parts):
    raw = '|'.join(str(p) for p in parts)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


def person_id(name, affiliation=''):
    return 'p_' + make_id(name.strip(), affiliation.strip())


def new_doc(corpus, source_type, url, title, text, name='', pid=None,
            **extra):
    doc = {
        'doc_id': corpus + '_' + make_id(url, title, name, text[:200]),
        'person_id': pid or (person_id(name, extra.get('school', ''))
                             if name else ''),
        'name': name,
        'corpus': corpus,
        'source_type': source_type,
        'url': url,
        'title': title,
        'text': text,
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
    }
    doc.update(extra)
    return doc


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records, append=False):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'a' if append else 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def merge_jsonl(path, records, key='doc_id'):
    """按 key 去重合并写入，已存在的记录被新记录覆盖。"""
    existing = {r[key]: r for r in read_jsonl(path)}
    for r in records:
        existing[r[key]] = r
    write_jsonl(path, existing.values())
    return len(existing)
