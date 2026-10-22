# -*- coding: UTF-8 -*-
"""由两个公开 GitHub 数据集生成 data/nobel/ 下的表格。

用法：
    git clone https://github.com/JeffersonConza/The_Nobel_Laureates
    git clone https://github.com/frishberg/Nobel-Prizes-by-Academic-Affiliations
    python3 data/build_nobel.py <The_Nobel_Laureates 目录> <Nobel-Prizes-by-Academic-Affiliations 目录>
"""

import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import unquote

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nobel')
STEM = {'Physics': 'phy', 'Chemistry': 'che', 'Medicine': 'med'}


def norm(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z]', '', s.lower())


def wiki_name(path):
    return unquote(path.rsplit('/', 1)[-1]).replace('_', ' ')


def load_prizes(path):
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    prizes = {}
    for r in rows:
        cat = 'Medicine' if r['category'].startswith('Physiology') else r['category']
        key = (r['laureate_id'], r['year'], cat)
        p = prizes.setdefault(key, {
            'laureate_id': r['laureate_id'], 'year': int(r['year']),
            'category': cat, 'laureate_type': r['laureate_type'],
            'full_name': r['full_name'], 'sex': r['sex'],
            'birth_date': r['birth_date'], 'birth_city': r['birth_city'],
            'birth_country': r['birth_country'], 'death_date': r['death_date'],
            'prize_share': r['prize_share'],
            'motivation': r['motivation'].strip('"'),
            'award_organizations': [],
        })
        org = r['organization_name'].strip()
        if org and org not in p['award_organizations']:
            p['award_organizations'].append(org)
    return list(prizes.values())


def main(prize_dir, aff_dir):
    os.makedirs(OUT, exist_ok=True)
    prizes = load_prizes(os.path.join(prize_dir, 'nobel_laureates_data.csv'))
    aff = json.load(open(os.path.join(aff_dir, 'data.json'), encoding='utf-8'))
    aff_by = defaultdict(list)
    for name, v in aff.items():
        aff_by[(norm(name), v['category'], v['year'])].append((name, v))
        aff_by[(norm(name), None, v['year'])].append((name, v))

    matched = 0
    for p in prizes:
        by = int(p['birth_date'][:4]) if p['birth_date'][:4].isdigit() else None
        p['birth_year'] = by
        p['age_at_award'] = p['year'] - by if by else None
        cat = 'Physiology or Medicine' if p['category'] == 'Medicine' else p['category']
        cands = aff_by.get((norm(p['full_name']), cat, p['year'])) or \
            aff_by.get((norm(p['full_name']), None, p['year']))
        if not cands:
            # 维基百科常用简称：按姓氏 + 年份 + 类别匹配，且只接受唯一候选
            last = norm(p['full_name'].split()[-1]) if p['full_name'] else ''
            pool = [(n, v) for n, v in aff.items() if v['year'] == p['year'] and
                    v['category'] in (cat, p['category']) and last and
                    norm(n).endswith(last)]
            cands = pool if len(pool) == 1 else None
        if cands:
            matched += 1
            name, v = cands[0]
            p['wiki_name'] = name
            p['wiki_url'] = v.get('link', '')
            p['alma_maters'] = [wiki_name(x) for x in v.get('alma_matters', [])]
            p['institutions'] = [wiki_name(x) for x in v.get('institutions', [])]
        else:
            p['wiki_name'] = p['wiki_url'] = ''
            p['alma_maters'], p['institutions'] = [], []

    fields = ['laureate_id', 'year', 'category', 'laureate_type', 'full_name',
              'sex', 'birth_year', 'birth_date', 'birth_city', 'birth_country',
              'death_date', 'age_at_award', 'prize_share', 'motivation',
              'award_organizations', 'wiki_name', 'wiki_url', 'alma_maters',
              'institutions']

    def write(path, rows):
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: '; '.join(v) if isinstance(v, list) else v
                            for k, v in r.items() if k in fields})

    prizes.sort(key=lambda r: (r['year'], r['category'], r['full_name']))
    write(os.path.join(OUT, 'laureates_all.csv'), prizes)
    stem = [p for p in prizes if p['category'] in STEM and
            p['laureate_type'] == 'Individual']
    write(os.path.join(OUT, 'laureates_stem.csv'), stem)

    # 采样框：每位 STEM 获奖者一行，附 nobel 子命令与诺奖官网页面的对应信息
    with open(os.path.join(OUT, 'crawl_frame_stem.csv'), 'w',
              encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['laureate_id', 'full_name', 'category_code', 'year',
                    'summary_page', 'api_query', 'status'])
        paths = {'Physics': 'physics', 'Chemistry': 'chemistry',
                 'Medicine': 'medicine'}
        for p in stem:
            w.writerow([p['laureate_id'], p['full_name'], STEM[p['category']],
                        p['year'], 'https://www.nobelprize.org/prizes/%s/%s/summary/'
                        % (paths[p['category']], p['year']),
                        'https://api.nobelprize.org/2.1/laureate/%s'
                        % p['laureate_id'], '未抓取'])

    stats = summarize(stem, matched, len(prizes))
    with open(os.path.join(OUT, 'stats.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats['overview'], ensure_ascii=False, indent=2))


def summarize(stem, matched, total):
    by_cat = Counter(p['category'] for p in stem)
    ages = [p['age_at_award'] for p in stem if p['age_at_award'] is not None]

    def med(v):
        v = sorted(v)
        n = len(v)
        return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)

    decades = defaultdict(list)
    for p in stem:
        if p['age_at_award'] is not None:
            decades['%ds' % (p['year'] // 10 * 10)].append(p['age_at_award'])
    alma = Counter(a for p in stem for a in p['alma_maters'])
    inst = Counter(a for p in stem for a in p['institutions'])
    award_org = Counter(o for p in stem for o in p['award_organizations'])
    birth = Counter(p['birth_country'] for p in stem if p['birth_country'])
    has_aff = [p for p in stem if p['alma_maters'] and p['institutions']]
    same = sum(1 for p in has_aff if set(p['alma_maters']) & set(p['institutions']))
    return {
        'overview': {
            'prizes_all_categories': total,
            'stem_individual_prizes': len(stem),
            'stem_by_category': dict(by_cat),
            'female_share_stem': round(sum(p['sex'] == 'Female' for p in stem) / len(stem), 3),
            'median_age_at_award': med(ages),
            'affiliation_match_rate_all': round(matched / total, 3),
            'stem_with_alma_and_institutions': len(has_aff),
            'share_worked_at_own_alma_mater': round(same / len(has_aff), 3) if has_aff else None,
        },
        'median_age_by_decade': {k: {'n': len(v), 'median_age': med(v)}
                                 for k, v in sorted(decades.items())},
        'top_alma_maters': alma.most_common(20),
        'top_institutions': inst.most_common(20),
        'top_award_organizations': award_org.most_common(20),
        'top_birth_countries': birth.most_common(15),
    }


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
