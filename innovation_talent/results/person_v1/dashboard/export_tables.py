# -*- coding: UTF-8 -*-
"""把 results/person_v1/results.json 整理成报告页面用的 5 张汇总表（不含任何个人信息）。
运行（innovation_talent 目录下）：python results/person_v1/dashboard/export_tables.py"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, ROOT)
from talent_corpus.model_params import DEF_DM, INDICATORS as MI  # noqa: E402

BASE = os.path.join(ROOT, 'results', 'person_v1')
OUT = os.path.join(BASE, 'dashboard')
LIFE = ['中学及以前', '本科', '研究生', '工作后']


def main():
    r = json.load(open(os.path.join(BASE, 'results.json'), encoding='utf-8'))
    ind = pd.DataFrame(r['indicators'])
    dims = {int(k): v for k, v in r['dims'].items()}
    cols, R = r['R']['cols'], np.array(r['R']['m'])
    dist = 1 - R
    np.fill_diagonal(dist, 0)
    lab = dict(zip(cols, fcluster(linkage(squareform(dist, checks=False), 'average'), 5, 'maxclust')))
    big = pd.Series(lab).value_counts().index[:2].tolist()

    def cname(c):
        if lab[c] not in big:
            return '未归入两大簇'
        return '方向与投入' if lab['C01'] == lab[c] else '问题发现与解决'

    prior = {i[0]: i[4] for i in MI}
    out = pd.DataFrame({'id': ind.id, 'name': ind.name, 'dim': ind.dim, 'dim_name': ind.dim.map(dims)})
    for c in ['cn_beh', 'nobel_beh', 'cn_beh_lo', 'cn_beh_hi', 'nobel_beh_lo', 'nobel_beh_hi',
              'cn_stmt_share', 'nobel_stmt_share', 'cn_share', 'nobel_share']:
        out[c] = ind[c].round(4)
    out['nobel_len_or'] = ind.nobel_or2x.round(3)
    out['stage_n'] = ind.n
    for j, k in enumerate(['s1', 's2', 's3', 's4']):
        out['enrich_' + k] = ind['enrich_' + LIFE[j]].round(3)
        out['prior_' + k] = [prior[c][j] for c in ind.id]
    out['prior_peak'], out['obs_peak'] = ind.prior_peak, ind.obs_peak
    ok = (ind.n >= 20) & (ind.prior_trend.abs() > 0.01)
    out['trend_agree'] = np.where(ok, np.where(np.sign(ind.prior_trend) == np.sign(ind.obs_trend), '一致', '相反'),
                                  '不判断')
    out['own_r'], out['other_r'] = ind.own_mean.round(3), ind.other_mean.round(3)
    out['cluster'] = [cname(c) for c in ind.id]
    out.to_csv(os.path.join(OUT, 'indicators.csv'), index=False, encoding='utf-8')

    dd = pd.DataFrame(r['dimensions']).rename(columns={'name': 'dim_name'})
    s2, s4 = np.array([x[1] for x in DEF_DM]), np.array([x[3] for x in DEF_DM])
    dd['model_s2'], dd['model_s4'] = (s2 / s2.sum()).round(4), (s4 / s4.sum()).round(4)
    dd[['dim', 'dim_name', 'k', 'cn_share', 'nobel_share', 'model_s2', 'model_s4']].round(4) \
        .to_csv(os.path.join(OUT, 'dimensions.csv'), index=False, encoding='utf-8')
    e = pd.DataFrame(r['edu_rows']).rename(columns={'name': 'dim_name'})
    e[['dim', 'dim_name', 'ug_mean', 'grad_mean', 'irr', 'lo', 'hi', 'p']].round(4) \
        .to_csv(os.path.join(OUT, 'education.csv'), index=False, encoding='utf-8')
    pd.DataFrame([{'a': a, 'b': b, 'r': round(float(R[i, j]), 3)} for i, a in enumerate(cols)
                  for j, b in enumerate(cols) if i != j]).to_csv(os.path.join(OUT, 'partial_r.csv'), index=False,
                                                                 encoding='utf-8')
    q, s, st, ed = r['quality'], r['stability'], r['structure'], r['education']
    summ = [
        ('n_people', q['n_people']), ('n_cn', q['n_cn']), ('n_nobel', q['n_nobel']),
        ('n_excluded', sum(q['excluded_honor_lists'].values())), ('n_judgements', q['n_judgements']),
        ('verified_rate', q['verified_rate']), ('behavior_rate', q['behavior_rate']),
        ('shared_quote_rate', q['shared_quote_rate']), ('shared_exact_rate', q['shared_exact_rate']),
        ('mean_beh_cn', q['mean_behavior']['cn']), ('mean_beh_nobel', q['mean_behavior']['nobel']),
        ('len_med_cn', q['len_median']['cn']), ('len_med_nobel', q['len_median']['nobel']),
        ('len_max_cn', q['len_range']['cn'][1]), ('len_min_nobel', q['len_range']['nobel'][0]),
        ('len_rho_cn', q['len_behavior_spearman']['cn']), ('len_rho_nobel', q['len_behavior_spearman']['nobel']),
        ('rho_nobel_short_long', s['nobel_short_vs_long']), ('rho_cn_short_long', s['cn_short_vs_long']),
        ('rho_cn_nobel', s['cn_vs_nobel']), ('r_same', st['mean_same']), ('r_diff', st['mean_diff']),
        ('r_p', round(st['mwu_p'], 3)), ('n_items', st['n_items']),
        ('trend_agree', int((out.trend_agree == '一致').sum())), ('trend_judged', int((out.trend_agree != '不判断').sum())),
        ('n_ug', ed['n_ug']), ('n_grad', ed['n_grad']),
        ('n_indicators_nobel_30', int((out.nobel_beh >= 0.3).sum())), ('n_indicators_cn_10', int((out.cn_beh >= 0.1).sum())),
        ('n_indicators_rare', int((out.nobel_beh < 0.15).sum())),
    ]
    pd.DataFrame(summ, columns=['metric', 'value']).to_csv(os.path.join(OUT, 'summary.csv'), index=False, encoding='utf-8')


if __name__ == '__main__':
    main()
