# -*- coding: UTF-8 -*-
"""按心理测量框架分析 person 级编码结果（persons.csv / codes.csv）。

输出九组表到 talent_data/person/analysis/：
    01_sample.csv            样本构成
    02_quality.csv           判断质量
    03_observability.csv     指标可观测性（出现率与 95% CI、声明比例）
    04_structure.csv         结构效度：指标间偏相关、聚类、主成分载荷
    05_dimension_alpha.csv   各维度内部一致性（Cronbach α）
    06_stage.csv             发展（阶段）效度：阶段富集与先验方向一致性
    07_composition.csv       组间/组内构成比较
    08_education.csv         本科生 vs 研究生（泊松回归，控制篇幅）
    09_robustness.csv        指标稳健性分级（R1—R6）

用法：python -m talent_corpus.person_analysis [--keep-honor]
只读本地 CSV，不调用模型。
"""

import argparse
import itertools
import json
import math
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from . import model_params as mp

DATA = os.path.join('talent_data', 'person')
OUT = os.path.join(DATA, 'analysis')

STAGES = ['中学及以前', '本科', '研究生', '工作后']
SKIP = {'C12', 'C13', 'C15', 'C17'}
CODES = [i[0] for i in mp.INDICATORS if i[0] not in SKIP]
DIM_OF = {i[0]: i[1] for i in mp.INDICATORS}
NAME_OF = {i[0]: i[2] for i in mp.INDICATORS}
PRIOR = {i[0]: i[4] for i in mp.INDICATORS}
GRADE = {i[0]: i[3] for i in mp.INDICATORS}


# ---------------------------------------------------------------- 读入

def load(exclude_honor=True):
    persons = pd.read_csv(os.path.join(DATA, 'persons.csv'), encoding='utf-8-sig')
    persons = persons[persons.coded == 1].copy()
    if exclude_honor:
        persons = persons[persons.text_type.fillna('') != '荣誉罗列或通报'].copy()
    persons['grp'] = np.where(persons.group == 'cn', 'cn', 'nobel')
    persons['logchars'] = np.log(persons.chars.clip(lower=1))
    codes = pd.read_csv(os.path.join(DATA, 'codes.csv'), encoding='utf-8-sig')
    codes = codes[codes.person_id.isin(persons.person_id)]
    return persons.reset_index(drop=True), codes


def behavior_matrix(persons, codes):
    """人 × 指标：是否有 level>=2 的行为证据（1/0）。"""
    m = pd.DataFrame(0, index=persons.person_id, columns=CODES)
    beh = codes[codes.level >= 2]
    for pid, ind in zip(beh.person_id, beh.indicator):
        if pid in m.index and ind in m.columns:
            m.at[pid, ind] = 1
    return m


def level_matrix(persons, codes):
    """人 × 指标：0 无、1 仅声明、2 行为。"""
    m = pd.DataFrame(0, index=persons.person_id, columns=CODES)
    for pid, ind, lv in zip(codes.person_id, codes.indicator, codes.level):
        if pid in m.index and ind in m.columns:
            m.at[pid, ind] = max(m.at[pid, ind], int(lv))
    return m


# ---------------------------------------------------------------- 统计工具

def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z ** 2 / n
    c = (p + z ** 2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def partial_spearman(x, y, z):
    """在 z 上回归掉秩次后的 Spearman 偏相关。"""
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
    A = sm.add_constant(rz)
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    if np.std(ex) == 0 or np.std(ey) == 0:
        return 0.0
    return float(np.corrcoef(ex, ey)[0, 1])


def cronbach_alpha(m):
    m = np.asarray(m, dtype=float)
    k = m.shape[1]
    if k < 2:
        return None
    item_var = m.var(axis=0, ddof=1).sum()
    total_var = m.sum(axis=1).var(ddof=1)
    return None if total_var == 0 else k / (k - 1) * (1 - item_var / total_var)


def varimax(load, iters=200, tol=1e-6):
    p, k = load.shape
    r = np.eye(k)
    d = 0
    for _ in range(iters):
        d_old = d
        L = load @ r
        u, s, vt = np.linalg.svd(load.T @ (L ** 3 - L @ np.diag((L ** 2).sum(axis=0)) / p))
        r = u @ vt
        d = s.sum()
        if d_old and d / d_old < 1 + tol:
            break
    return load @ r


# ---------------------------------------------------------------- 各表

def sample_table(persons):
    rows = []
    for g, label in (('cn', '国内获奖学生'), ('nobel', '诺贝尔奖得主')):
        d = persons[persons.grp == g]
        q1, q3 = d.chars.quantile([.25, .75])
        rows.append({'组别': label, '人数': len(d), '材料篇数': int(d.n_texts.sum()),
                     '篇幅中位数': int(d.chars.median()),
                     '篇幅四分位距': '%d—%d' % (q1, q3),
                     '子集': ';'.join('%s:%d' % (k, v) for k, v in
                                      d.subsets.fillna('').value_counts().items())})
    return pd.DataFrame(rows)


def quality_table(codes):
    n = len(codes)
    v = int(codes.verified.sum())
    beh = int((codes.level == 2).sum())
    shared = int((codes.shared_quote.fillna(0) > 0).sum())
    exact = int((codes.shared_quote.fillna(0) == 1).sum())
    rows = [('指标判断条数', n, ''),
            ('引语可核实', '%d（%.1f%%）' % (v, 100 * v / n), '引语在所发材料中逐字出现'),
            ('判为具体行为', '%d（%.1f%%）' % (beh, 100 * beh / n), '其余为仅声明'),
            ('与其他指标共用引语', '%d（%.1f%%）' % (shared, 100 * shared / n), 'shared_quote>=1'),
            ('完全相同引语', '%d（%.1f%%）' % (exact, 100 * exact / n), 'shared_quote=1')]
    return pd.DataFrame(rows, columns=['指标', '数值', '含义'])


def observability(persons, beh, lev):
    rows = []
    for ind in CODES:
        r = {'指标': ind, '名称': NAME_OF[ind], '类别': DIM_OF[ind]}
        for g in ('nobel', 'cn'):
            ids = persons.loc[persons.grp == g, 'person_id']
            k, n = int(beh.loc[ids, ind].sum()), len(ids)
            lo, hi = wilson(k, n)
            decl = int((lev.loc[ids, ind] == 1).sum())
            r['%s_人数' % g] = k
            r['%s_出现率' % g] = round(100 * k / n, 1)
            r['%s_CI' % g] = '%.0f—%.0f' % (lo * 100, hi * 100) if lo is not None else ''
            r['%s_声明率' % g] = round(100 * decl / n, 1)
        rows.append(r)
    return pd.DataFrame(rows)


def structure(persons, lev, n_perm=500):
    """诺奖组：控制篇幅的指标间偏相关、同类 vs 异类、聚类、主成分。"""
    ids = persons.loc[persons.grp == 'nobel', 'person_id']
    M = lev.loc[ids]
    z = persons.set_index('person_id').loc[ids, 'logchars'].values
    corr = pd.DataFrame(np.eye(len(CODES)), index=CODES, columns=CODES)
    for a, b in itertools.combinations(CODES, 2):
        r = partial_spearman(M[a].values.astype(float), M[b].values.astype(float), z)
        corr.at[a, b] = corr.at[b, a] = r
    same, diff = [], []
    for a, b in itertools.combinations(CODES, 2):
        (same if DIM_OF[a] == DIM_OF[b] else diff).append(corr.at[a, b])
    same_m, diff_m = float(np.mean(same)), float(np.mean(diff))
    dims = np.array([DIM_OF[c] for c in CODES])
    iu = np.triu_indices(len(CODES), 1)
    vals = corr.values[iu]
    rng = np.random.default_rng(20261030)
    perm = []
    for _ in range(n_perm):
        d = rng.permutation(dims)
        m = np.array([d[i] == d[j] for i, j in zip(*iu)])
        perm.append(vals[m].mean() - vals[~m].mean())
    p_perm = (float(np.sum(np.array(perm) >= same_m - diff_m)) + 1) / (n_perm + 1)

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    D = 1 - corr.values
    np.fill_diagonal(D, 0)
    Z = linkage(squareform(D, checks=False), method='average')
    cluster = fcluster(Z, t=2, criterion='maxclust')

    R = corr.values
    w, v = np.linalg.eigh(R)
    idx = np.argsort(w)[::-1]
    w, v = w[idx], v[:, idx]
    load = varimax(v[:, :2] * np.sqrt(w[:2]))
    order = np.argsort(-np.abs(load[:, 0]))
    load = load[order]
    codes_sorted = [CODES[i] for i in order]
    var_exp = w[:2] / w.sum() * 100

    st = pd.DataFrame({
        '指标': codes_sorted,
        '名称': [NAME_OF[c] for c in codes_sorted],
        '类别': [DIM_OF[c] for c in codes_sorted],
        '聚类': [int(cluster[CODES.index(c)]) for c in codes_sorted],
        '成分1载荷': [round(float(load[i, 0]), 3) for i in range(len(codes_sorted))],
        '成分2载荷': [round(float(load[i, 1]), 3) for i in range(len(codes_sorted))],
    })
    summary = {'同类平均偏相关': round(same_m, 3), '异类平均偏相关': round(diff_m, 3),
               '差值': round(same_m - diff_m, 3), '置换检验p': round(p_perm, 4),
               '成分1解释率%': round(float(var_exp[0]), 1),
               '成分2解释率%': round(float(var_exp[1]), 1)}
    return st, corr, summary


def alpha_table(beh):
    rows = []
    for d in sorted(mp.DIMS):
        cols = [c for c in CODES if DIM_OF[c] == d]
        a = cronbach_alpha(beh[cols].values)
        rows.append({'维度': '%d %s' % (d, mp.DIMS[d]), '指标数': len(cols),
                     'Cronbach α': None if a is None else round(a, 3),
                     '平均出现率%': round(100 * beh[cols].values.mean(), 1)})
    a = cronbach_alpha(beh[CODES].values)
    rows.append({'维度': '全部 %d 项（仅供参考）' % len(CODES), '指标数': len(CODES),
                 'Cronbach α': None if a is None else round(a, 3),
                 '平均出现率%': round(100 * beh[CODES].values.mean(), 1)})
    return pd.DataFrame(rows)


def stage_table(persons, codes):
    """诺奖组：行为证据的阶段分布（富集度），与模型先验方向对照。"""
    nobel_ids = set(persons.loc[persons.grp == 'nobel', 'person_id'])
    c = codes[(codes.level == 2) & codes.person_id.isin(nobel_ids)
              & codes.stage.isin(STAGES)]
    total = c.stage.value_counts(normalize=True)
    rows = []
    for ind in CODES:
        sub = c[c.indicator == ind]
        if len(sub) < 5:
            rows.append({'指标': ind, '名称': NAME_OF[ind], '类别': DIM_OF[ind],
                         '证据条数': len(sub), '阶段富集（log2）': '证据不足',
                         '经验趋势': '', '先验趋势': '', '方向一致': ''})
            continue
        share = sub.stage.value_counts(normalize=True).reindex(STAGES).fillna(0)
        enrich = {s: (math.log2(share[s] / total[s]) if share[s] > 0 and total[s] > 0 else np.nan)
                  for s in STAGES}
        emp = enrich['工作后'] - enrich['中学及以前']
        prior = float(np.polyfit(range(4), PRIOR[ind], 1)[0])
        rows.append({'指标': ind, '名称': NAME_OF[ind], '类别': DIM_OF[ind],
                     '证据条数': len(sub),
                     '阶段富集（log2）': '；'.join('%s %.1f' % (s, enrich[s]) for s in STAGES),
                     '经验趋势': '上升' if emp > 0.3 else ('下降' if emp < -0.3 else '平'),
                     '先验趋势': '上升' if prior > 0 else '下降',
                     '方向一致': ('是' if (emp > 0) == (prior > 0) else '否')
                     if abs(emp) > 0.3 else '平'})
    df = pd.DataFrame(rows)
    judged = df[df['方向一致'].isin(['是', '否'])]
    return df, int((judged['方向一致'] == '是').sum()), len(judged)


def composition_table(persons, codes):
    """构成：每个维度占本组行为证据的比例。"""
    c = codes[codes.level == 2].copy()
    c['dim'] = c.indicator.map(DIM_OF)
    out, thirds = {}, {}
    for g in ('cn', 'nobel'):
        ids = set(persons.loc[persons.grp == g, 'person_id'])
        out[g] = c[c.person_id.isin(ids)].dim.value_counts(normalize=True) \
            .reindex(sorted(mp.DIMS)).fillna(0)
        d = persons[persons.grp == g].sort_values('chars')
        parts = np.array_split(d.person_id.values, 3)
        thirds[g] = [c[c.person_id.isin(p)].dim.value_counts(normalize=True)
                     .reindex(sorted(mp.DIMS)).fillna(0) for p in parts]
    df = pd.DataFrame({'维度': ['%d %s' % (d, mp.DIMS[d]) for d in sorted(mp.DIMS)],
                       '国内学生占比%': (out['cn'].values * 100).round(1),
                       '诺奖占比%': (out['nobel'].values * 100).round(1)})
    extra = pd.DataFrame([
        {'维度': '（诺奖组内）篇幅最短 vs 最长三分位的构成相关', '国内学生占比%': '',
         '诺奖占比%': round(float(stats.spearmanr(thirds['nobel'][0], thirds['nobel'][2])[0]), 2)},
        {'维度': '（国内组内）篇幅最短 vs 最长三分位的构成相关',
         '国内学生占比%': round(float(stats.spearmanr(thirds['cn'][0], thirds['cn'][2])[0]), 2),
         '诺奖占比%': ''},
        {'维度': '两组构成的相关', '国内学生占比%': '', '诺奖占比%':
         round(float(stats.spearmanr(out['cn'].values, out['nobel'].values)[0]), 2)}])
    return pd.concat([df, extra], ignore_index=True)


def education_table(persons, codes):
    """国内学生：本科 vs 研究生（硕士+博士），每维度行为证据数，泊松回归控制篇幅。"""
    cn = persons[persons.grp == 'cn'].copy()
    cn['lvl'] = np.select(
        [cn.education.eq('本科'), cn.education.isin(['硕士', '博士', '博士后或已工作'])],
        ['本科', '研究生'], default='其他')
    cn = cn[cn.lvl != '其他']
    c = codes[(codes.level == 2) & codes.person_id.isin(cn.person_id)].copy()
    c['dim'] = c.indicator.map(DIM_OF)
    cnt = c.groupby(['person_id', 'dim']).size().unstack(fill_value=0) \
        .reindex(sorted(mp.DIMS), axis=1).fillna(0)
    d = cn[['person_id', 'lvl', 'logchars']].set_index('person_id').join(cnt).fillna(0)
    rows = []
    for dim in sorted(mp.DIMS):
        d['y'] = d[dim]
        try:
            m = smf.glm('y ~ C(lvl, Treatment("本科"))', data=d,
                        family=sm.families.Poisson(), offset=d.logchars).fit()
            k = 'C(lvl, Treatment("本科"))[T.研究生]'
            b, se, p = m.params[k], m.bse[k], m.pvalues[k]
            irr = '%.2f（%.2f—%.2f）' % (math.exp(b), math.exp(b - 1.96 * se),
                                        math.exp(b + 1.96 * se))
        except Exception:
            irr, p = '', np.nan
        rows.append({'维度': '%d %s' % (dim, mp.DIMS[dim]),
                     '本科生均值': round(float(d.loc[d.lvl == '本科', dim].mean()), 2),
                     '研究生均值': round(float(d.loc[d.lvl == '研究生', dim].mean()), 2),
                     '发生率比（95%CI）': irr,
                     'p': '' if np.isnan(p) else round(float(p), 3)})
    meta = pd.DataFrame([{'维度': '样本人数', '本科生均值': int((cn.lvl == '本科').sum()),
                          '研究生均值': int((cn.lvl == '研究生').sum()),
                          '发生率比（95%CI）': '', 'p': ''}])
    return pd.concat([meta, pd.DataFrame(rows)], ignore_index=True)


# ---------------------------------------------------------------- 因素分析

TWO_FACTOR = {1: 1, 6: 1, 2: 2, 3: 2, 4: 2, 5: 2}      # 维度 → 两因子模型的因子编号


def factor_analysis(persons, beh, tag='nobel', min_prev=0.03):
    """平行分析 → EFA → CFA（1/2/6 因子）→ ω。

    只在指定组内做：两个来源的文本异质，混在一起做因素分析会把"文体差异"读成"因子结构"。
    出现率过低（<min_prev）或过高的指标在该组内几乎是常数，相关矩阵不稳定，先剔除并在
    结果里列出剔除名单。保留指标不足 12 项时不做因素分析。
    """
    from . import factor_models as fm

    ids = persons.loc[persons.grp == tag, 'person_id']
    M = beh.loc[ids]
    n = len(M)
    prev = M.mean()
    keep = [c for c in CODES if min_prev <= prev[c] <= 1 - min_prev]
    dropped = [c for c in CODES if c not in keep]
    base = {'组': tag, 'n': n, '保留指标数': len(keep), '剔除指标': '、'.join(dropped)}
    if len(keep) < 12:
        return dict(base, skipped='保留指标仅 %d 项，样本不足以做因素分析' % len(keep))

    X = M[keep].values.astype(float)
    R = np.corrcoef(X, rowvar=False)
    counts = X.mean(axis=0)

    obs, rand = fm.parallel_analysis(R, n)
    R_te = fm.tetrachoric(R, counts)
    obs_te, rand_te = fm.parallel_analysis(R_te, n)
    k_pa = fm.n_factors_by_pa(obs, rand)
    k_pa_te = fm.n_factors_by_pa(obs_te, rand_te)

    fac = pd.DataFrame({'指标': keep, '名称': [NAME_OF[c] for c in keep],
                        '维度': [DIM_OF[c] for c in keep],
                        '出现率%': (counts * 100).round(1),
                        '特征值': np.round(obs, 3),
                        '随机95分位': np.round(rand, 3),
                        '四分相关特征值': np.round(obs_te, 3),
                        '四分相关随机95分位': np.round(rand_te, 3)})

    k_use = int(min(max(k_pa, 1), 6))
    load, h2 = fm.paf(R, k_use)
    efa = pd.DataFrame(np.round(load, 3),
                       columns=['因子%d' % (i + 1) for i in range(k_use)])
    efa.insert(0, '指标', keep)
    efa.insert(1, '名称', [NAME_OF[c] for c in keep])
    efa.insert(2, '维度', [DIM_OF[c] for c in keep])
    efa['共同度'] = np.round(h2, 3)

    models = {
        '单因子': [(i, 0) for i in range(len(keep))],
        '两因子（方向投入/问题求解）': [(i, TWO_FACTOR[DIM_OF[c]] - 1)
                                        for i, c in enumerate(keep)],
        '六因子（模型原设）': [(i, DIM_OF[c] - 1) for i, c in enumerate(keep)],
    }
    fits, loads, om_table = [], {}, pd.DataFrame()
    for name, pairs in models.items():
        try:
            r = fm.cfa_ml(R, pairs, n)
        except Exception as e:                      # 不收敛时记录原因，不中断
            fits.append({'模型': name, 'χ²': '', 'df': '', 'p': '', 'CFI': '',
                         'TLI': '', 'RMSEA': '', 'SRMR': '', 'AIC': '', 'BIC': '',
                         '参数数': '', '备注': '未收敛：%s' % e})
            continue
        fits.append({'模型': name, 'χ²': round(r['chi2'], 2), 'df': r['df'],
                     'p': round(r['p'], 4), 'CFI': round(r['CFI'], 3),
                     'TLI': round(r['TLI'], 3), 'RMSEA': round(r['RMSEA'], 3),
                     'SRMR': round(r['SRMR'], 3), 'AIC': round(r['AIC'], 1),
                     'BIC': round(r['BIC'], 1), '参数数': r['n_par'], '备注': ''})
        loads[name] = r['loadings_std']
        if name == '六因子（模型原设）':
            om = fm.omega(r['loadings_std'])
            om_table = pd.DataFrame([
                {'维度': '%d %s' % (d, mp.DIMS[d]),
                 '指标数': int(sum(1 for c in keep if DIM_OF[c] == d)),
                 'McDonald ω': (None if d == 3 else round(float(om[d - 1]), 3)),
                 '组内 Cronbach α': (
                     None if sum(1 for c in keep if DIM_OF[c] == d) < 2 else
                     round(float(cronbach_alpha(
                         M[[c for c in keep if DIM_OF[c] == d]].values.astype(float))), 3))}
                for d in sorted(mp.DIMS)])
    fit_df = pd.DataFrame(fits)

    lrow = []
    for i, c in enumerate(keep):
        row = {'指标': c, '名称': NAME_OF[c], '维度': DIM_OF[c]}
        for name, L in loads.items():
            vals = ['F%d=%.2f' % (f + 1, L[i, f]) for f in range(L.shape[1])
                    if abs(L[i, f]) > 0.005]
            row[name] = '；'.join(vals) or '—'
        lrow.append(row)
    return dict(base, pa=fac, k_pa=k_pa, k_pa_te=k_pa_te, efa=efa, fit=fit_df,
                loadings=pd.DataFrame(lrow), omega=om_table, skipped='')


def robustness(persons, codes, obs, corr, beh):
    """R1—R6 六条标准 → A/B/C 分级。

    R1 可观测：诺奖 >=20%、国内 >=5% 的人有行为证据；
    R2 是行为而非声明：两组“只有声明”的比例都 <=20%；
    R3 可区分：与其他指标共用引语的判断 <=50%；
    R4 归属本类：控制篇幅后，与本类平均偏相关高于与他类；
    R5 篇幅稳健：诺奖最短与最长三分位中，该指标占本组证据的 log2 比值 <=0.75；
    R6 跨组稳定：两组构成占比的 log2 比值 <=1。
    A：R1、R2 满足且 R3—R6 至少满足 3 条；C：诺奖组不足 15%（文本测不到）。
    """
    thirds = np.array_split(persons[persons.grp == 'nobel']
                            .sort_values('chars').person_id.values, 3)
    cn_ids = persons.loc[persons.grp == 'cn', 'person_id']
    nb_ids = persons.loc[persons.grp == 'nobel', 'person_id']
    rows = []
    for ind in CODES:
        d = obs[obs['指标'] == ind].iloc[0]
        nb_rate, cn_rate = d['nobel_出现率'], d['cn_出现率']
        r1 = nb_rate >= 20 and cn_rate >= 5
        r2 = d['nobel_声明率'] <= 20 and d['cn_声明率'] <= 20
        sub = codes[codes.indicator == ind]
        r3 = bool(len(sub)) and float((sub.shared_quote.fillna(0) > 0).mean()) <= 0.5
        same = [corr.at[ind, b] for b in CODES if b != ind and DIM_OF[b] == DIM_OF[ind]]
        diff = [corr.at[ind, b] for b in CODES if DIM_OF[b] != DIM_OF[ind]]
        r4 = float(np.mean(same)) > float(np.mean(diff))
        shares = []
        for part in thirds:
            blk = beh.loc[beh.index.isin(part)]
            shares.append((blk[ind].sum() + 1e-3) / (blk.values.sum() + 1e-3))
        r5 = bool(abs(math.log2(shares[0] / shares[2])) <= 0.75)
        cn_share = (beh.loc[beh.index.isin(cn_ids), ind].sum() + 1e-3) / (
            beh.loc[beh.index.isin(cn_ids)].values.sum() + 1e-3)
        nb_share = (beh.loc[beh.index.isin(nb_ids), ind].sum() + 1e-3) / (
            beh.loc[beh.index.isin(nb_ids)].values.sum() + 1e-3)
        r6 = bool(abs(math.log2(cn_share / nb_share)) <= 1)
        met = sum(1 for x in (r3, r4, r5, r6) if x)
        if nb_rate < 15:
            grade = 'C 文本测不到'
        elif r1 and r2 and met >= 3:
            grade = 'A 稳健'
        else:
            grade = 'B 有缺陷'
        miss = [t for t, ok in (('证据过少', r1), ('多为声明', r2), ('与相邻指标难分', r3),
                                ('不归本类', r4), ('随篇幅变化', r5), ('两组构成差异大', r6))
                if not ok]
        rows.append({'指标': ind, '名称': NAME_OF[ind], '类别': DIM_OF[ind],
                     '诺奖观测率%': nb_rate, '国内观测率%': cn_rate,
                     'R1': int(r1), 'R2': int(r2), 'R3': int(r3),
                     'R4': int(r4), 'R5': int(r5), 'R6': int(r6),
                     '等级': grade, '未达标': '；'.join(miss) or '—'})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep-honor', action='store_true', help='不排除“荣誉罗列或通报”的人')
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)

    persons, codes = load(exclude_honor=not args.keep_honor)
    beh, lev = behavior_matrix(persons, codes), level_matrix(persons, codes)
    print('分析样本 %d 人（国内 %d，诺奖 %d），判断 %d 条' % (
        len(persons), int((persons.grp == 'cn').sum()),
        int((persons.grp == 'nobel').sum()), len(codes)))

    t1 = sample_table(persons)
    t2 = quality_table(codes)
    t3 = observability(persons, beh, lev)
    t4, corr, s4 = structure(persons, lev)
    t5 = alpha_table(beh)
    t6, agree, judged = stage_table(persons, codes)
    t7 = composition_table(persons, codes)
    t8 = education_table(persons, codes)
    t9 = robustness(persons, codes, t3, corr, beh)
    fa = factor_analysis(persons, beh, 'nobel')
    fa_cn = factor_analysis(persons, beh, 'cn')

    outputs = [('01_sample', t1), ('02_quality', t2), ('03_observability', t3),
               ('04_structure', t4), ('05_dimension_alpha', t5), ('06_stage', t6),
               ('07_composition', t7), ('08_education', t8), ('09_robustness', t9)]
    fits_all = []
    for tag, fa_g in (('nobel', fa), ('cn', fa_cn)):
        if fa_g.get('skipped'):
            print('  %s 组跳过因素分析：%s' % (tag, fa_g['skipped']))
            continue
        print('  %s 组：保留 %d 项（剔除 %s）；平行分析建议 %d 个因子'
              % (tag, fa_g['保留指标数'], fa_g['剔除指标'] or '无', fa_g['k_pa']))
        outputs += [('10_factorability_' + tag, fa_g['pa']),
                    ('11_efa_loadings_' + tag, fa_g['efa']),
                    ('12_cfa_loadings_' + tag, fa_g['loadings']),
                    ('14_omega_' + tag, fa_g['omega'])]
        fits_all.append(fa_g['fit'].assign(组='%s（n=%d）' % (
            '诺奖组' if tag == 'nobel' else '国内组', fa_g['n'])))
    if fits_all:
        cols = ['组', '模型', 'χ²', 'df', 'p', 'CFI', 'TLI', 'RMSEA', 'SRMR',
                'AIC', 'BIC', '参数数', '备注']
        outputs.append(('13_cfa_fit', pd.concat(fits_all)[cols]))
    fsum = {}
    for tag, fa_g in (('nobel', fa), ('cn', fa_cn)):
        if fa_g.get('skipped'):
            fsum[tag] = {'跳过': fa_g['skipped']}
            continue
        fsum[tag] = {'n': fa_g['n'], '保留指标数': fa_g['保留指标数'],
                     '剔除指标': fa_g['剔除指标'],
                     '平行分析因子数（φ）': fa_g['k_pa'],
                     '平行分析因子数（四分相关）': fa_g['k_pa_te']}
    with open(os.path.join(OUT, 'factor_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(fsum, f, ensure_ascii=False, indent=1)
        print('  因子数摘要：', json.dumps(fsum, ensure_ascii=False))
    for name, df in outputs:
        path = os.path.join(OUT, name + '.csv')
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print('  %-24s %d 行 → %s' % (name, len(df), path))

    with open(os.path.join(OUT, 'structure_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(s4, f, ensure_ascii=False, indent=1)
    print('\n结构：同类 %.3f vs 异类 %.3f（差 %.3f，置换 p=%.3f）；PC1 %.1f%%，PC2 %.1f%%'
          % (s4['同类平均偏相关'], s4['异类平均偏相关'], s4['差值'],
             s4['置换检验p'], s4['成分1解释率%'], s4['成分2解释率%']))
    print('阶段方向一致：%d / %d 项' % (agree, judged))
    print('稳健性分级：', t9['等级'].value_counts().to_dict())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
