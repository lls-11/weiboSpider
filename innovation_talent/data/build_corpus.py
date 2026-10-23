# -*- coding: UTF-8 -*-
"""由 data/raw/ 中的抓取原文生成整理后的数据与初步统计。

在 innovation_talent/ 目录下运行：
    python3 data/build_corpus.py
输入：
    data/raw/rmrb_lists_raw.jsonl   rmrb --dump-raw 保存的名录原文
    data/raw/nobel_pages_raw.jsonl  nobel 子命令抓取的页面（未清洗）
输出见 data/README.md。
"""

import csv
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from talent_corpus import corpus  # noqa: E402
from talent_corpus.analysis import build_persons  # noqa: E402
from talent_corpus.preprocess import Tagger, prepare  # noqa: E402
from talent_corpus.sources import nobel, rmrb  # noqa: E402

RAW = os.path.join(HERE, 'raw')
OUT_RMRB = os.path.join(HERE, 'rmrb_scholarship')
OUT_NOBEL = os.path.join(HERE, 'nobel', 'texts')
OUT_STATS = os.path.join(HERE, 'initial_stats')
LEVEL_CN = {'undergraduate': '本专科生', 'graduate': '研究生'}
PERIOD_CN = {'P0': '学前与小学', 'P1': '中学', 'P2': '本科', 'P3': '硕士与博士',
             'P4': '博士后与青年研究者', 'P5': '独立研究期'}


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def build_rmrb():
    arts = rmrb.dedupe_articles(rmrb.articles_from_dump(
        corpus.read_jsonl(os.path.join(RAW, 'rmrb_lists_raw.jsonl'))))
    docs = [d for a in arts for d in rmrb.to_docs(a)]
    corpus.write_jsonl(os.path.join(OUT_RMRB, 'entries.jsonl'), docs)
    write_csv(os.path.join(OUT_RMRB, 'entries.csv'), docs,
              ['person_id', 'name', 'school', 'program', 'grade', 'level',
               'award_year', 'publish_date', 'page', 'text', 'url', 'doc_id'])
    summary = Counter((d['publish_date'], d['level'], d['award_year'],
                       d['title']) for d in docs)
    write_csv(os.path.join(OUT_RMRB, 'list_summary.csv'),
              [{'publish_date': k[0], 'level': LEVEL_CN.get(k[1], k[1]),
                'award_year': k[2], 'title': k[3], 'n_entries': n}
               for k, n in sorted(summary.items())],
              ['publish_date', 'level', 'award_year', 'title', 'n_entries'])
    return docs


def build_nobel():
    docs = [nobel.clean_doc(d) for d in corpus.read_jsonl(
        os.path.join(RAW, 'nobel_pages_raw.jsonl'))]
    for d in docs:
        d['too_short'] = len(d['text']) < 300
        d['has_text'] = not d['pdf_only'] and not d['too_short']
    by_type = defaultdict(list)
    for d in docs:
        if d['has_text']:
            by_type[d['source_type']].append(d)
    for t, ds in by_type.items():
        corpus.write_jsonl(os.path.join(OUT_NOBEL, t + '.jsonl'),
                           sorted(ds, key=lambda x: (x['award_year'], x['name'])))
    write_csv(os.path.join(HERE, 'nobel', 'text_index.csv'),
              [dict(d, chars=len(d['text'])) for d in
               sorted(docs, key=lambda x: (x['award_year'], x['name'],
                                           x['source_type']))],
              ['doc_id', 'laureate_id', 'name', 'category', 'award_year',
               'source_type', 'narrative_voice', 'chars', 'has_text',
               'pdf_only', 'too_short', 'url'])
    return [d for d in docs if d['has_text']]


def stats(rmrb_docs, nobel_docs):
    tagger = Tagger()
    prepared = [prepare(d, tagger) for d in rmrb_docs + nobel_docs]
    persons = build_persons(prepared)
    write_csv(os.path.join(OUT_STATS, 'persons_sample_type.csv'),
              persons.values(),
              ['person_id', 'name', 'corpus', 'level', 'school', 'award_year',
               'n_docs', 'sample_type', 'innovation', 'stage'])
    # 国奖样本的类型分布
    rows = []
    for level in ('undergraduate', 'graduate'):
        ps = [p for p in persons.values() if p['corpus'] == 'rmrb_scholarship'
              and p['level'] == level]
        c = Counter(p['sample_type'] for p in ps)
        for t, n in c.most_common():
            rows.append({'level': LEVEL_CN[level], 'sample_type': t, 'n': n,
                         'share': round(n / len(ps), 3)})
        rows.append({'level': LEVEL_CN[level], 'sample_type': '（创新型合计）',
                     'n': sum(p['innovation'] for p in ps),
                     'share': round(sum(p['innovation'] for p in ps) / len(ps), 3)})
    write_csv(os.path.join(OUT_STATS, 'sample_type_summary.csv'), rows,
              ['level', 'sample_type', 'n', 'share'])
    # 各类文本的事件句、口号句、第一人称比例
    groups = defaultdict(list)
    for d in prepared:
        key = d['corpus'] + ':' + (LEVEL_CN.get(d.get('level'), '') or
                                   d['source_type'])
        groups[key].append(d)
    rows = []
    for k, ds in sorted(groups.items()):
        n = len(ds)
        rows.append({
            'group': k, 'n_docs': n,
            'median_chars': sorted(len(d['text']) for d in ds)[n // 2],
            'event_ratio': round(sum(d['stats']['event_ratio'] for d in ds) / n, 3),
            'rhetoric_ratio': round(sum(d['stats']['rhetoric_ratio'] for d in ds) / n, 3),
            'self_ratio': round(sum(d['stats']['self_ratio'] for d in ds) / n, 3),
        })
    write_csv(os.path.join(OUT_STATS, 'text_profile.csv'), rows,
              ['group', 'n_docs', 'median_chars', 'event_ratio',
               'rhetoric_ratio', 'self_ratio'])
    # 诺奖自传覆盖了哪些人生时期（按时期关键词，启发式）
    bios = [d for d in prepared if d['source_type'] == 'biographical']
    rows = []
    for code, label in PERIOD_CN.items():
        for voice in ('self', 'narrator', 'all'):
            ds = [d for d in bios if voice == 'all' or d['narrative_voice'] == voice]
            k = sum(1 for d in ds if any(s['period'] == code and s['period_explicit']
                                         for s in d['sentences']))
            rows.append({'period': code, 'label': label, 'voice': voice,
                         'n_bios': len(ds), 'n_mentioning': k,
                         'share': round(k / len(ds), 3) if ds else None})
    write_csv(os.path.join(OUT_STATS, 'nobel_bio_period_coverage.csv'), rows,
              ['period', 'label', 'voice', 'n_bios', 'n_mentioning', 'share'])
    # 国奖事迹中的高频成就信号
    from talent_corpus import load_lexicon
    signals = load_lexicon()['sample_type_signals']
    rows = []
    stu = [d for d in prepared if d['corpus'] == 'rmrb_scholarship']
    for t, words in signals.items():
        for w in words:
            n = sum(1 for d in stu if w in d['text'])
            if n:
                rows.append({'type': t, 'signal': w, 'n_entries': n,
                             'share': round(n / len(stu), 3)})
    rows.sort(key=lambda r: -r['n_entries'])
    write_csv(os.path.join(OUT_STATS, 'scholarship_signal_counts.csv'), rows,
              ['type', 'signal', 'n_entries', 'share'])
    schools = Counter(d['school'] for d in rmrb_docs)
    write_csv(os.path.join(OUT_STATS, 'scholarship_schools.csv'),
              [{'school': s, 'n_entries': n} for s, n in schools.most_common()],
              ['school', 'n_entries'])
    return persons


def build_criteria(docs):
    """国奖事迹中的可量化成就（候选校标），见 talent_corpus/criteria.py。"""
    from talent_corpus import criteria
    rows = []
    for d in docs:
        x = criteria.extract(d['text'])
        x.update({k: d.get(k, '') for k in ('person_id', 'doc_id', 'name', 'school',
                                            'level', 'award_year', 'grade')})
        x['field'] = criteria.field_of(d.get('program', ''), d.get('school', ''))
        x['doctoral'] = '博士' in d.get('program', '')
        rows.append(x)
    fields = ['person_id', 'doc_id', 'name', 'school', 'field', 'level', 'doctoral',
              'award_year', 'grade', 'papers', 'papers_first_author',
              'top_journal_mention', 'patents', 'patents_granted',
              'software_copyrights', 'projects_led', 'awards', 'awards_international',
              'awards_national', 'awards_provincial', 'award_top_level',
              'award_best_grade', 'honors', 'volunteer_hours',
              'national_scholarship_times', 'venture', 'truncated']
    out = os.path.join(HERE, 'criteria')
    write_csv(os.path.join(out, 'scholarship_criteria.csv'), rows, fields)
    num = ['papers', 'papers_first_author', 'patents_granted', 'software_copyrights',
           'projects_led', 'awards', 'awards_national', 'awards_international',
           'honors', 'volunteer_hours']
    summary = []
    for level in ('undergraduate', 'graduate'):
        g = [x for x in rows if x['level'] == level]
        for k in num:
            v = sorted(x[k] for x in g)
            nz = [a for a in v if a]
            summary.append({
                'level': LEVEL_CN[level], 'measure': k, 'n': len(v),
                'nonzero_share': round(len(nz) / len(v), 3),
                'median_nonzero': nz[len(nz) // 2] if nz else '',
                'p90': v[int(0.9 * len(v))], 'max': v[-1]})
    write_csv(os.path.join(out, 'criteria_summary.csv'), summary,
              ['level', 'measure', 'n', 'nonzero_share', 'median_nonzero', 'p90',
               'max'])
    return rows


def build_long_texts():
    """高校与清华特奖长篇报道：去重、按人切分，见 talent_corpus/segment.py。"""
    from talent_corpus import segment
    docs = corpus.read_jsonl(os.path.join(RAW, 'long_text_articles_raw.jsonl'))
    # 同一标题保留最长的一篇（腾讯新闻、智源社区的转载只有片段或与官网重复）
    best = {}
    for d in docs:
        key = d['title'].split('-')[0].strip()
        if key not in best or len(d['text']) > len(best[key]['text']):
            best[key] = d
    docs = [d for d in best.values() if len(d['text']) >= 500]
    tagger = Tagger()
    persons = [prepare(p, tagger) for p in segment.segment_docs(docs)]
    out = os.path.join(HERE, 'long_texts')
    corpus.write_jsonl(os.path.join(out, 'persons.jsonl'),
                       [{k: v for k, v in p.items() if k not in ('sentences', 'stats')}
                        for p in persons])
    write_csv(os.path.join(out, 'index.csv'),
              [dict(p, chars=len(p['text']), n_sentences=p['stats']['n_sentences'])
               for p in persons],
              ['doc_id', 'person_id', 'name', 'school', 'corpus', 'segment', 'chars',
               'n_sentences', 'title', 'url', 'parent_doc_id'])
    return docs, persons


def main():
    build_long_texts()
    r = build_rmrb()
    build_criteria(r)
    n = build_nobel()
    persons = stats(r, n)
    print('名录条目', len(r), '诺奖文本', len(n), '人物', len(persons))


if __name__ == '__main__':
    main()
