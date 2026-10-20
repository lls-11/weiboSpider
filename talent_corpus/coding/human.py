# -*- coding: UTF-8 -*-
"""人工编码：导出阅读表与编码模板，导入人工编码结果。

导入后的记录与大模型编码记录格式相同，可直接用 analysis.reliability 计算一致性。
建议至少抽取 15%–20% 的文档双人独立编码，一致性达标后再用模型编码全量样本。
"""

import csv
import os
import random
from datetime import datetime

CODE_FIELDS = ['doc_id', 'indicator', 'anchor_stage', 'evidence_quality',
               'sentence_ids', 'life_period', 'attribution', 'note']


def sample_docs(docs, frac=0.2, min_per_group=5, seed=2026, key='corpus'):
    """按语料组分层抽样。"""
    rnd = random.Random(seed)
    groups = {}
    for d in docs:
        groups.setdefault(d.get(key, ''), []).append(d)
    out = []
    for g in sorted(groups):
        items = sorted(groups[g], key=lambda d: d['doc_id'])
        k = min(len(items), max(min_per_group, round(len(items) * frac)))
        out.extend(rnd.sample(items, k))
    return out


def export_sheets(docs, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'reading_sheet.csv'), 'w',
              encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['doc_id', 'name', 'corpus', 'sid', 'kind_heuristic',
                    'period_heuristic', 'sentence'])
        for d in docs:
            for s in d['sentences']:
                w.writerow([d['doc_id'], d.get('name', ''), d.get('corpus', ''),
                            s['sid'], s['kind'], s['period'], s['text']])
    with open(os.path.join(out_dir, 'codes_template.csv'), 'w',
              encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow(CODE_FIELDS)
    return len(docs)


def import_codes(path, docs_by_id, coder):
    """读取人工编码表；sentence_ids 用分号分隔，如 S003;S007。

    docs_by_id 只应包含交给该编码员的文档：没有任何编码行的文档也会生成一条
    空记录，表示“读过、未发现证据”，计算一致性时不能漏掉。
    """
    by_doc = {}
    with open(path, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            did = (row.get('doc_id') or '').strip()
            if did not in docs_by_id or not row.get('indicator'):
                continue
            doc = docs_by_id[did]
            sents = {s['sid']: s['text'] for s in doc['sentences']}
            ev = []
            for sid in (row.get('sentence_ids') or '').replace('；', ';') \
                    .split(';'):
                sid = sid.strip().upper()
                if sid in sents:
                    ev.append({'sentence_id': sid, 'quote': sents[sid],
                               'life_period': (row.get('life_period') or
                                               'PX').strip(),
                               'attribution': (row.get('attribution') or
                                               'narrator').strip()})
            if not ev:
                continue
            by_doc.setdefault(did, []).append({
                'indicator': row['indicator'].strip().upper(),
                'anchor_stage': int(row['anchor_stage']),
                'evidence_quality': int(row['evidence_quality']),
                'evidence': ev,
                'rationale': row.get('note', '')})
    now = datetime.now().isoformat(timespec='seconds')
    return [{'doc_id': did, 'person_id': docs_by_id[did].get('person_id', ''),
             'coder': coder, 'coded_at': now, 'error': '',
             'codes': by_doc.get(did, []), 'local_codes': [],
             'rhetoric_sentence_ids': []}
            for did in docs_by_id]
