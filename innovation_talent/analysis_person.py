# -*- coding: UTF-8 -*-
"""以人为单位编码结果（talent_data/person/）的探索性分析，结果写入 results/person_v1/。

分析顺序（每一步回答一个问题）：
1. 数据质量：判断是否可信（引语核对、共用引语、声明与行为的比例）。
2. 观测性：每项指标在多少人身上能看到行为证据。
3. 篇幅：指标数与篇幅的关系。两组篇幅完全不重叠（国内最长 3,944 字，诺奖最短 6,403 字符），
   所以组间不比绝对数量，只比“构成”（各指标占本组全部行为证据的比例），并先检验构成是否随篇幅变化。
4. 结构：控制篇幅后，同一类别的指标是否比不同类别的更常一起出现。
5. 阶段：每项指标的行为证据集中在哪个人生阶段，与模型的阶段相关度先验对照。
6. 组内比较：国内本科生与研究生（篇幅相近、文体相同）在各类别上的差异，对照模型的类别 × 阶段权重。

运行：python analysis_person.py   （需要 numpy、pandas、scipy、statsmodels）
"""
import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from talent_corpus.model_params import DEF_DM, DIMS, INDICATORS as MODEL_IND

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'talent_data', 'person')
OUT = os.path.join(HERE, 'results', 'person_v1')

IND = ['C%02d' % i for i in range(1, 34) if i not in (12, 13, 15, 17)]
NAME = {i[0]: i[2] for i in MODEL_IND}
DIM = {i[0]: i[1] for i in MODEL_IND}
PRIOR_S = {i[0]: i[4] for i in MODEL_IND}
LIFE = ['中学及以前', '本科', '研究生', '工作后']


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def load():
    P = pd.read_csv(os.path.join(SRC, 'persons.csv'), encoding='utf-8-sig')
    C = pd.read_csv(os.path.join(SRC, 'codes.csv'), encoding='utf-8-sig')
    excluded = P[P.text_type != '过程叙述'].group.value_counts().to_dict()   # 只记人数，不写姓名
    P = P[P.text_type == '过程叙述'].copy()
    C = C[C.person_id.isin(P.person_id)].copy()
    for c in IND:
        P['b_' + c] = (P[c] == 2).astype(int)
    P['log_len'] = np.log(P['chars_sent'])
    return P, C, excluded


def quality(P, C, excluded):
    runs = [json.loads(line) for line in open(os.path.join(SRC, 'runs.jsonl'), encoding='utf-8')]
    ok = {}
    for r in runs:
        if not r.get('error'):
            ok[r['person_id']] = r
    models = pd.Series([r['model'] for r in ok.values()]).value_counts().to_dict()
    return {
        'n_people': int(len(P)), 'n_cn': int((P.group == 'cn').sum()), 'n_nobel': int((P.group == 'nobel').sum()),
        'excluded_honor_lists': {k: int(v) for k, v in excluded.items()},
        'n_judgements': int(len(C)),
        'verified_rate': round(float(C.verified.mean()), 3),
        'behavior_rate': round(float((C.level == 2).mean()), 3),
        'shared_quote_rate': round(float((C.shared_quote > 0).mean()), 3),
        'shared_exact_rate': round(float((C.shared_quote == 1).mean()), 3),
        'models': models,
        'failed_runs': int(sum(1 for r in runs if r.get('error'))),
        'mean_behavior': P.groupby('group').n_behavior.mean().round(2).to_dict(),
        'mean_statement': P.groupby('group').n_statement.mean().round(2).to_dict(),
        'len_median': P.groupby('group').chars_sent.median().round(0).to_dict(),
        'len_range': {g: [int(d.chars_sent.min()), int(d.chars_sent.max())] for g, d in P.groupby('group')},
        'len_behavior_spearman': {g: round(float(stats.spearmanr(d.chars_sent, d.n_behavior)[0]), 2)
                                  for g, d in P.groupby('group')},
    }


def prevalence(P):
    rows = []
    for c in IND:
        r = {'id': c, 'name': NAME[c], 'dim': DIM[c]}
        for g, d in P.groupby('group'):
            n = len(d)
            kb = int((d[c] == 2).sum())
            ks = int((d[c] == 1).sum())
            lo, hi = wilson(kb, n)
            r.update({g + '_beh': kb / n, g + '_beh_lo': lo, g + '_beh_hi': hi,
                      g + '_stmt': ks / n,
                      g + '_stmt_share': ks / (ks + kb) if ks + kb else None})
        rows.append(r)
    return pd.DataFrame(rows)


def composition(P):
    """各指标占本组全部行为证据的比例；并检验诺奖组内构成是否随篇幅三分位变化。"""
    def comp(d):
        tot = d[['b_' + c for c in IND]].sum()
        return (tot / tot.sum()).values

    cn, nb = P[P.group == 'cn'], P[P.group == 'nobel']
    comp_cn, comp_nb = comp(cn), comp(nb)
    tert = pd.qcut(nb.chars_sent, 3, labels=['短', '中', '长'])
    by_t = {t: comp(nb[tert == t]) for t in ['短', '中', '长']}
    tert_cn = pd.qcut(cn.chars_sent, 3, labels=['短', '中', '长'])
    by_t_cn = {t: comp(cn[tert_cn == t]) for t in ['短', '中', '长']}
    rho = lambda a, b: round(float(stats.spearmanr(a, b)[0]), 2)  # noqa: E731
    stab = {'nobel_short_vs_long': rho(by_t['短'], by_t['长']),
            'cn_short_vs_long': rho(by_t_cn['短'], by_t_cn['长']),
            'cn_vs_nobel': rho(comp_cn, comp_nb),
            'nobel_short_vs_cn_long': rho(by_t['短'], by_t_cn['长'])}
    df = pd.DataFrame({'id': IND, 'name': [NAME[c] for c in IND], 'dim': [DIM[c] for c in IND],
                       'cn_share': comp_cn, 'nobel_share': comp_nb})
    eps = 0.004
    df['log2_ratio'] = np.log2((df.nobel_share + eps) / (df.cn_share + eps))
    # 类别层面：类别内各指标份额之和，再除以该类可编码指标数（每个指标的平均份额）
    dim_rows = []
    for d in range(1, 7):
        sub = df[df.dim == d]
        dim_rows.append({'dim': d, 'name': DIMS[d], 'k': int(len(sub)),
                         'cn_share': float(sub.cn_share.sum()), 'nobel_share': float(sub.nobel_share.sum())})
    return df, pd.DataFrame(dim_rows), stab


def length_effect(P):
    """组内：每项指标出现（行为）与篇幅（对数）的关系，篇幅翻倍时优势比。"""
    import statsmodels.api as sm
    rows = []
    for c in IND:
        r = {'id': c}
        for g, d in P.groupby('group'):
            y = d['b_' + c]
            if y.sum() < 5 or y.sum() > len(y) - 5:
                r[g + '_or2x'] = None
                continue
            try:
                m = sm.Logit(y, sm.add_constant(d['log_len'])).fit(disp=0)
                r[g + '_or2x'] = float(np.exp(m.params['log_len'] * np.log(2)))
                r[g + '_p'] = float(m.pvalues['log_len'])
            except Exception:
                r[g + '_or2x'] = None
        rows.append(r)
    return pd.DataFrame(rows)


def structure(P):
    """诺奖组（n 较大、篇幅充分）：控制篇幅后的指标间偏相关；同类与异类的平均相关。"""
    d = P[P.group == 'nobel']
    cols = [c for c in IND if 8 <= d['b_' + c].sum() <= len(d) - 8]
    X = d[['b_' + c for c in cols]].values.astype(float)
    L = np.column_stack([np.ones(len(d)), d.log_len.values])
    beta, *_ = np.linalg.lstsq(L, X, rcond=None)
    R = np.corrcoef((X - L @ beta).T)
    item = []
    for i, c in enumerate(cols):
        own = [R[i, j] for j, c2 in enumerate(cols) if j != i and DIM[c2] == DIM[c]]
        oth = [R[i, j] for j, c2 in enumerate(cols) if DIM[c2] != DIM[c]]
        by_dim = {}
        for dd in range(1, 7):
            v = [R[i, j] for j, c2 in enumerate(cols) if j != i and DIM[c2] == dd]
            if v:
                by_dim[dd] = float(np.mean(v))
        best = max(by_dim, key=by_dim.get)
        item.append({'id': c, 'dim': DIM[c], 'own_mean': float(np.mean(own)) if own else None,
                     'other_mean': float(np.mean(oth)), 'closest_dim': int(best),
                     'closest_r': by_dim[best]})
    iu = np.triu_indices(len(cols), 1)
    same = [R[a, b] for a, b in zip(*iu) if DIM[cols[a]] == DIM[cols[b]]]
    diff = [R[a, b] for a, b in zip(*iu) if DIM[cols[a]] != DIM[cols[b]]]
    t = stats.mannwhitneyu(same, diff, alternative='greater')
    summary = {'n_items': len(cols), 'excluded_rare': [c for c in IND if c not in cols],
               'mean_same': round(float(np.mean(same)), 3), 'mean_diff': round(float(np.mean(diff)), 3),
               'n_same_pairs': len(same), 'mwu_p': float(t.pvalue)}
    return cols, R, pd.DataFrame(item), summary


def stage_profile(C):
    """行为证据（已核实、阶段已知）在四个人生阶段的分布；相对富集 = 该指标的阶段比例 ÷ 全部证据的阶段比例。"""
    out = {}
    for g in ['nobel', 'cn']:
        d = C[(C.group == g) & (C.level == 2) & (C.verified == 1) & (C.stage.isin(LIFE))]
        base = d.stage.value_counts(normalize=True).reindex(LIFE).fillna(0)
        rows = []
        for c in IND:
            s = d[d.indicator == c].stage.value_counts().reindex(LIFE).fillna(0)
            n = int(s.sum())
            share = s / n if n else s
            enrich = (share / base.replace(0, np.nan)).fillna(0)
            prior = PRIOR_S[c]
            rho = float(stats.spearmanr(prior, enrich.values)[0]) if n >= 10 and g == 'nobel' else None
            rows.append({'id': c, 'n': n, **{'share_' + k: float(share[k]) for k in LIFE},
                         **{'enrich_' + k: float(enrich[k]) for k in LIFE},
                         'prior_peak': LIFE[int(np.argmax(prior))] if len(set(prior)) > 1 else '无差别',
                         'obs_peak': LIFE[int(np.argmax(enrich.values))] if n else None,
                         'prior_trend': float(np.polyfit(range(4), prior, 1)[0]),
                         'obs_trend': float(np.polyfit(range(4), enrich.values, 1)[0]) if n else None,
                         'rho_prior': rho})
        out[g] = {'base': base.round(3).to_dict(), 'rows': pd.DataFrame(rows)}
    return out


def cn_education(P):
    """国内组：研究生（硕、博）与本科生的类别差异，控制篇幅（泊松回归），对照模型类别权重的阶段变化。"""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    d = P[(P.group == 'cn') & (P.education.isin(['本科', '硕士', '博士']))].copy()
    d['grad'] = (d.education != '本科').astype(int)
    rows = []
    for k in range(1, 7):
        col = 'D%d_behavior' % k
        try:
            m = smf.glm('%s ~ grad + log_len' % col, data=d, family=sm.families.Poisson()).fit()
            irr, lo, hi = np.exp(m.params['grad']), *np.exp(m.conf_int().loc['grad'])
            p = float(m.pvalues['grad'])
        except Exception:
            irr = lo = hi = p = None
        rows.append({'dim': k, 'name': DIMS[k], 'ug_mean': float(d[d.grad == 0][col].mean()),
                     'grad_mean': float(d[d.grad == 1][col].mean()), 'irr': irr, 'lo': lo, 'hi': hi, 'p': p,
                     'model_s2': DEF_DM[k - 1][1], 'model_s3': DEF_DM[k - 1][2]})
    return {'n_ug': int((d.grad == 0).sum()), 'n_grad': int((d.grad == 1).sum()),
            'len_ug': float(d[d.grad == 0].chars_sent.median()),
            'len_grad': float(d[d.grad == 1].chars_sent.median()), 'rows': pd.DataFrame(rows)}


def main():
    os.makedirs(OUT, exist_ok=True)
    P, C, excluded = load()
    q = quality(P, C, excluded)
    prev = prevalence(P)
    comp, comp_dim, stab = composition(P)
    leff = length_effect(P)
    cols, R, item, struct = structure(P)
    stage = stage_profile(C)
    edu = cn_education(P)

    prev.merge(comp[['id', 'cn_share', 'nobel_share', 'log2_ratio']], on='id') \
        .merge(leff, on='id').merge(stage['nobel']['rows'], on='id') \
        .to_csv(os.path.join(OUT, 'indicators.csv'), index=False, encoding='utf-8-sig')
    comp_dim.to_csv(os.path.join(OUT, 'dimensions.csv'), index=False, encoding='utf-8-sig')
    item.to_csv(os.path.join(OUT, 'structure_items.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(R, index=cols, columns=cols).round(3).to_csv(os.path.join(OUT, 'structure_partial_r.csv'),
                                                              encoding='utf-8-sig')
    edu['rows'].to_csv(os.path.join(OUT, 'cn_education.csv'), index=False, encoding='utf-8-sig')

    res = {'quality': q, 'stability': stab, 'structure': struct,
           'stage_base': {g: stage[g]['base'] for g in stage},
           'education': {k: v for k, v in edu.items() if k != 'rows'},
           'indicators': json.loads(prev.merge(comp, on=['id', 'name', 'dim']).merge(leff, on='id')
                                    .merge(stage['nobel']['rows'], on='id')
                                    .merge(stage['cn']['rows'][['id', 'n'] + ['share_' + k for k in LIFE]]
                                           .rename(columns=lambda x: x if x == 'id' else 'cn_' + x), on='id')
                                    .merge(item, on=['id', 'dim'], how='left').to_json(orient='records')),
           'dimensions': json.loads(comp_dim.to_json(orient='records')),
           'edu_rows': json.loads(edu['rows'].to_json(orient='records')),
           'R': {'cols': cols, 'm': np.round(R, 3).tolist()},
           'def_dm': DEF_DM, 'dims': DIMS}
    with open(os.path.join(OUT, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ('quality', 'stability', 'structure', 'stage_base', 'education')},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
