# -*- coding: UTF-8 -*-
"""从编码结果到可分析的数据。

主要输出：
1. 人物 × 指标得分表，格式与 Excel《学生得分》一致，可直接粘贴；
2. 按模型权重计算的六维画像、综合参考分与覆盖率；
3. 阶段显著性：把科学家叙事中的证据按人生时期归入 TAD 阶段，
   与模型的“阶段相关度”先验比较（方向一致性、Spearman 相关）；
4. 组间比较：创新型与非创新型学生、学生与科学家同期叙事；
5. 编码一致性（Cohen's kappa、加权 kappa）；
6. 本土化编码与刻板叙事比例的分组统计。
"""

import csv
import os
from collections import Counter, defaultdict

from . import classify, codable_indicators, load_codebook, model_params, stats

DEFAULT_LEVELS = ('高', '中')


# ---------------------------------------------------------------- 人物与阶段

def default_stage(p):
    """人物所处阶段的默认判定：依据学段与经历，而不是综合分。可用 CSV 覆盖。"""
    if p.get('corpus') == 'nobel':
        return 4.0
    level = p.get('level', '')
    if level == 'graduate':
        return 3.0 if '博士' in p.get('program', '') else 2.5
    if level == 'vocational':
        return 1.5
    return 2.0


def build_persons(docs, stage_overrides=None):
    by_pid = defaultdict(list)
    for d in docs:
        by_pid[d.get('person_id') or d['doc_id']].append(d)
    persons = {}
    for pid, ds in by_pid.items():
        first = next((d for d in ds if d['corpus'] == 'rmrb_scholarship'), ds[0])
        merged = {'sentences': [s for d in ds for s in d.get('sentences', [])]}
        cls = classify.classify(merged)
        p = {
            'person_id': pid, 'name': first.get('name', ''),
            'corpus': first.get('corpus', ''), 'level': first.get('level', ''),
            'program': first.get('program', ''), 'school': first.get('school', ''),
            'category': first.get('category', ''),
            'award_year': first.get('award_year', ''),
            'n_docs': len(ds), 'doc_ids': [d['doc_id'] for d in ds],
            'sample_type': cls['primary'], 'innovation': cls['innovation'],
        }
        p['stage'] = (stage_overrides or {}).get(pid) or default_stage(p)
        persons[pid] = p
    return persons


def read_stage_overrides(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return {r['person_id']: float(r['stage']) for r in csv.DictReader(f)
                if r.get('stage')}


# ---------------------------------------------------------------- 编码汇总

def pick_coder(records):
    c = Counter(r['coder'] for r in records if not r.get('error'))
    return c.most_common(1)[0][0] if c else None


def person_codes(records, persons, coder=None, min_quality=2, periods=None,
                 codebook=None):
    """{person_id: {指标: {anchor, quality, n_evidence, periods}}}。

    同一人物多篇文档取最高锚点；periods 给定时只计这些人生时期的证据，
    例如 {'P2', 'P3'} 只看本科与研究生时期，用于学生与科学家同期比较。
    """
    coder = coder or pick_coder(records)
    doc_owner = {did: pid for pid, p in persons.items() for did in p['doc_ids']}
    out = defaultdict(dict)
    for r in records:
        if r.get('error') or r['coder'] != coder:
            continue
        pid = doc_owner.get(r['doc_id'])
        if pid is None:
            continue
        for c in r.get('codes', []):
            if c['evidence_quality'] < min_quality:
                continue
            ev = [e for e in c['evidence'] if periods is None or
                  e.get('life_period') in periods]
            if not ev:
                continue
            cur = out[pid].get(c['indicator'])
            if cur is None:
                cur = out[pid][c['indicator']] = {
                    'anchor': 0, 'quality': 0, 'n_evidence': 0,
                    'periods': set()}
            cur['anchor'] = max(cur['anchor'], c['anchor_stage'])
            cur['quality'] = max(cur['quality'], c['evidence_quality'])
            cur['n_evidence'] += len(ev)
            cur['periods'].update(e.get('life_period', 'PX') for e in ev)
    return out


def score_table(pcodes, persons, scale='anchor', levels=DEFAULT_LEVELS,
                pool=None):
    """人物 × 指标 0–100 分；未编码记为 None。

    scale='anchor'：锚点 × 25（锚点 1–4 → 25–100），属于标准参照；
    scale='percentile'：在 pool（默认全部人物）内取中位秩百分位，需要样本量足够。
    """
    ids = codable_indicators(levels)
    table = {pid: {i: None for i in ids} for pid in persons}
    for pid, codes in pcodes.items():
        if pid not in table:
            continue
        for i, c in codes.items():
            if i in table[pid]:
                table[pid][i] = c['anchor']
    if scale == 'anchor':
        for row in table.values():
            for i, v in row.items():
                row[i] = None if v is None else v * 25
        return table
    pool = set(pool or persons)
    for i in ids:
        vals = [table[p][i] for p in pool if table[p][i] is not None]
        n = len(vals)
        for p in table:
            v = table[p][i]
            if v is None or n == 0:
                continue
            below = sum(1 for x in vals if x < v)
            equal = sum(1 for x in vals if x == v)
            table[p][i] = round((below + 0.5 * equal) / n * 100, 1)
    return table


def profiles(table, persons, levels=DEFAULT_LEVELS, **model_kwargs):
    only = set(codable_indicators(levels))
    rows = []
    for pid, scores in table.items():
        p = persons[pid]
        r = model_params.evaluate(scores, p['stage'], only=only,
                                  **model_kwargs)
        row = {k: p[k] for k in ('person_id', 'name', 'corpus', 'level',
                                 'school', 'category', 'sample_type',
                                 'innovation', 'stage')}
        for d, v in r['dims'].items():
            row['dim%d' % d] = None if v['score'] is None else \
                round(v['score'], 1)
            row['dim%d_cov' % d] = round(v['coverage'], 3)
        row['composite'] = None if r['composite'] is None else \
            round(r['composite'], 1)
        row['coverage'] = round(r['coverage'], 3)
        row['n_indicators'] = sum(v is not None for v in scores.values())
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 阶段显著性

def stage_salience(records, persons, corpora=('nobel', ), coder=None,
                   min_quality=2, levels=DEFAULT_LEVELS, codebook=None):
    """把证据按人生时期归入 TAD 阶段，计算各指标在各阶段叙事中的出现率。

    出现率 = 在该阶段叙事中出现该指标证据的人数 ÷ 该阶段有任何证据的人数。
    返回 (指标行, 类别行, 汇总)。这是叙事显著性，不是预测效度，
    只能作为修正“阶段相关度”先验的初步依据。
    """
    cb = codebook or load_codebook()
    period_stage = {k: v['tad_stage'] for k, v in cb['life_periods'].items()}
    coder = coder or pick_coder(records)
    ids = codable_indicators(levels, cb)
    owner = {did: pid for pid, p in persons.items() for did in p['doc_ids']
             if p['corpus'] in corpora}
    seen = defaultdict(set)
    stage_people = defaultdict(set)
    for r in records:
        if r.get('error') or r['coder'] != coder or r['doc_id'] not in owner:
            continue
        pid = owner[r['doc_id']]
        for c in r.get('codes', []):
            if c['evidence_quality'] < min_quality or c['indicator'] not in ids:
                continue
            for e in c['evidence']:
                s = period_stage.get(e.get('life_period'))
                if s:
                    seen[(c['indicator'], s)].add(pid)
                    stage_people[s].add(pid)
    rows = []
    prior_cells, emp_cells = [], []
    for iid in ids:
        rel = model_params.IND_BY_ID[iid][4]
        prev = [len(seen[(iid, s)]) / len(stage_people[s])
                if stage_people[s] else 0.0 for s in (1, 2, 3, 4)]
        row = {'indicator': iid, 'name': model_params.IND_BY_ID[iid][2]}
        for s in (1, 2, 3, 4):
            row['prior_s%d' % s] = rel[s - 1]
            row['prev_s%d' % s] = round(prev[s - 1], 3)
            row['n_s%d' % s] = len(seen[(iid, s)])
        row['prior_slope'] = round(stats.slope(rel), 3)
        emp_slope = stats.slope(prev) if any(prev) else None
        row['emp_slope'] = None if emp_slope is None else round(emp_slope, 3)
        row['direction_agree'] = None if not emp_slope else \
            (emp_slope > 0) == (row['prior_slope'] > 0)
        rho = stats.spearman(list(rel), prev) if any(prev) else None
        row['spearman'] = None if rho is None else round(rho, 3)
        rows.append(row)
        if any(prev):
            mp, me = sum(rel) / 4, sum(prev) / 4
            prior_cells += [v / mp for v in rel]
            emp_cells += [v / me for v in prev]
    # 类别层面：各阶段证据在六类之间的分布 vs 类别 × 阶段先验权重
    dim_rows = []
    for d in model_params.DIMS:
        dids = [i for i in ids if model_params.IND_BY_ID[i][1] == d]
        row = {'dim': d, 'name': model_params.DIMS[d]}
        for s in (1, 2, 3, 4):
            tot = sum(len(seen[(i, s)]) for i in ids) or 1
            row['emp_share_s%d' % s] = round(
                sum(len(seen[(i, s)]) for i in dids) / tot, 3)
            row['prior_share_s%d' % s] = round(
                model_params.dim_shares(s)[d], 3)
        dim_rows.append(row)
    agree = [r['direction_agree'] for r in rows if r['direction_agree'] is not None]
    summary = {
        'coder': coder, 'corpora': list(corpora),
        'persons_per_stage': {s: len(stage_people[s]) for s in (1, 2, 3, 4)},
        'indicators_with_evidence': len(agree),
        'direction_agreement_rate': round(sum(agree) / len(agree), 3)
        if agree else None,
        'pooled_shape_spearman': None if len(prior_cells) < 3 else
        round(stats.spearman(prior_cells, emp_cells), 3),
    }
    return rows, dim_rows, summary


# ---------------------------------------------------------------- 组间比较

def group_compare(profile_rows, table, key, a, b, levels=DEFAULT_LEVELS):
    """比较两组人物的类别得分（Mann–Whitney、Cliff's δ）与各指标出现率。"""
    ga = [r for r in profile_rows if r.get(key) == a]
    gb = [r for r in profile_rows if r.get(key) == b]
    out = []
    for col in ['dim%d' % d for d in model_params.DIMS] + ['composite']:
        xa = [r[col] for r in ga if r[col] is not None]
        xb = [r[col] for r in gb if r[col] is not None]
        u, p = stats.mann_whitney(xa, xb)
        out.append({'measure': col, 'type': 'score', 'n_a': len(xa),
                    'n_b': len(xb), 'median_a': stats.median(xa),
                    'median_b': stats.median(xb),
                    'cliffs_delta': _r(stats.cliffs_delta(xa, xb)),
                    'U': _r(u), 'p': _r(p)})
    for iid in codable_indicators(levels):
        ka = sum(1 for r in ga if table[r['person_id']][iid] is not None)
        kb = sum(1 for r in gb if table[r['person_id']][iid] is not None)
        out.append({'measure': iid, 'type': 'presence', 'n_a': len(ga),
                    'n_b': len(gb),
                    'rate_a': _r(ka / len(ga)) if ga else None,
                    'rate_b': _r(kb / len(gb)) if gb else None,
                    'p': _r(stats.two_prop_z(ka, len(ga), kb, len(gb)))})
    return out


def _r(v, nd=3):
    return None if v is None else round(v, nd)


# ---------------------------------------------------------------- 一致性

def reliability(records, coder_a, coder_b, min_quality=2,
                levels=DEFAULT_LEVELS):
    """两名编码者（人或模型）在共同文档上的一致性。"""
    def index(coder):
        out = {}
        for r in records:
            if r['coder'] == coder and not r.get('error'):
                out[r['doc_id']] = {c['indicator']: c['anchor_stage']
                                    for c in r.get('codes', [])
                                    if c['evidence_quality'] >= min_quality}
        return out

    A, B = index(coder_a), index(coder_b)
    shared = sorted(set(A) & set(B))
    rows, pa_all, pb_all = [], [], []
    for iid in codable_indicators(levels):
        pa = [int(iid in A[d]) for d in shared]
        pb = [int(iid in B[d]) for d in shared]
        both = [(A[d][iid], B[d][iid]) for d in shared
                if iid in A[d] and iid in B[d]]
        pa_all += pa
        pb_all += pb
        rows.append({
            'indicator': iid, 'n_docs': len(shared),
            'present_a': sum(pa), 'present_b': sum(pb),
            'agreement': _r(sum(x == y for x, y in zip(pa, pb)) / len(shared))
            if shared else None,
            'kappa_presence': _r(stats.cohen_kappa(pa, pb, categories=[0, 1])),
            'n_both': len(both),
            'wkappa_anchor': _r(stats.cohen_kappa(
                [x for x, _ in both], [y for _, y in both],
                weights='quadratic', categories=[1, 2, 3, 4]))
            if len(both) >= 2 else None,
        })
    summary = {'coder_a': coder_a, 'coder_b': coder_b, 'n_docs': len(shared),
               'pooled_kappa_presence': _r(stats.cohen_kappa(
                   pa_all, pb_all, categories=[0, 1]))}
    return rows, summary


# ---------------------------------------------------------------- 本土化与刻板叙事

def local_code_summary(records, persons, coder=None):
    coder = coder or pick_coder(records)
    owner = {did: pid for pid, p in persons.items() for did in p['doc_ids']}
    has = defaultdict(set)
    new_labels = Counter()
    for r in records:
        if r.get('error') or r['coder'] != coder:
            continue
        pid = owner.get(r['doc_id'])
        if pid is None:
            continue
        for lc in r.get('local_codes', []):
            has[(persons[pid]['corpus'], lc['code'])].add(pid)
            if lc['code'] == 'NEW' and lc.get('label'):
                new_labels[(persons[pid]['corpus'], lc['label'])] += 1
    n_by_corpus = Counter(p['corpus'] for p in persons.values())
    codes = [c['id'] for c in load_codebook()['local_codes']] + ['NEW']
    rows = []
    for corpus_name, n in sorted(n_by_corpus.items()):
        row = {'corpus': corpus_name, 'n_persons': n}
        for c in codes:
            row[c] = _r(len(has[(corpus_name, c)]) / n)
        rows.append(row)
    top_new = [{'corpus': k[0], 'label': k[1], 'count': v}
               for k, v in new_labels.most_common(50)]
    return rows, top_new


def rhetoric_summary(docs, records, coder=None):
    coder = coder or pick_coder(records)
    llm = {r['doc_id']: len(r.get('rhetoric_sentence_ids', []))
           for r in records if r['coder'] == coder and not r.get('error')}
    groups = defaultdict(list)
    for d in docs:
        groups[d['corpus']].append(d)
    rows = []
    for g, ds in sorted(groups.items()):
        n = len(ds)
        heur = [d['stats']['rhetoric_ratio'] for d in ds if d['doc_id'] in llm]
        model = [llm[d['doc_id']] / (d['stats']['n_sentences'] or 1)
                 for d in ds if d['doc_id'] in llm]
        rows.append({
            'corpus': g, 'n_docs': n,
            'event_ratio': _r(sum(d['stats']['event_ratio'] for d in ds) / n),
            'rhetoric_ratio': _r(sum(d['stats']['rhetoric_ratio']
                                     for d in ds) / n),
            'self_ratio': _r(sum(d['stats']['self_ratio'] for d in ds) / n),
            'llm_rhetoric_ratio': _r(sum(model) / len(model)) if model else None,
            'heuristic_vs_llm_spearman': _r(stats.spearman(heur, model))
            if len(model) >= 3 else None,
        })
    return rows


# ---------------------------------------------------------------- 导出

def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(v) for k, v in r.items()})


def _cell(v):
    if isinstance(v, (set, list, tuple)):
        return ';'.join(str(x) for x in sorted(v))
    return v


def score_sheet_rows(table, persons):
    """转成 Excel《学生得分》的版式：行为 C01–C33，列为人物。"""
    pids = sorted(table, key=lambda p: (persons[p]['corpus'], p))
    header = {'编号': '所处 TAD 阶段', '类别编号': '', '指标': ''}
    header.update({p: persons[p]['stage'] for p in pids})
    rows = [header]
    for iid, dim, name, _, _ in model_params.INDICATORS:
        row = {'编号': iid, '类别编号': dim, '指标': name}
        for p in pids:
            row[p] = table[p].get(iid)
        rows.append(row)
    return rows, ['编号', '类别编号', '指标'] + pids


def export(out_dir, sheets):
    """sheets: {名称: (rows, fields)}；同时写 CSV 与（若安装 openpyxl）xlsx。"""
    os.makedirs(out_dir, exist_ok=True)
    for name, (rows, fields) in sheets.items():
        write_csv(os.path.join(out_dir, name + '.csv'), rows, fields)
    try:
        from openpyxl import Workbook
    except ImportError:
        return None
    wb = Workbook()
    wb.remove(wb.active)
    for name, (rows, fields) in sheets.items():
        rows = list(rows)
        if not rows:
            continue
        ws = wb.create_sheet(name[:31])
        fields = fields or list(rows[0].keys())
        ws.append(fields)
        for r in rows:
            ws.append([_cell(r.get(k)) for k in fields])
    path = os.path.join(out_dir, 'analysis.xlsx')
    wb.save(path)
    return path
