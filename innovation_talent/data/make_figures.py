# -*- coding: UTF-8 -*-
"""根据 analysis 目录的 CSV 画报告用的图（matplotlib，无第三方美化库）。

用法：python data/make_figures.py
输出到 talent_data/person/analysis/figures/：
    fig1_observability.png   各指标行为证据出现率（诺奖 95%CI + 国内点）
    fig2_scree_parallel.png  碎石图与平行分析
    fig3_cfa_loadings.png    六因子模型的标准化载荷
    fig4_composition.png     六维构成比（两组）
    fig5_stage_heatmap.png   各指标行为证据的阶段富集
"""

import os
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

A = os.path.join('talent_data', 'person', 'analysis')
OUT = os.path.join(A, 'figures')
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150


def load(name):
    return pd.read_csv(os.path.join(A, name + '.csv'), encoding='utf-8-sig')


def fig_observability():
    d = load('03_observability').sort_values('nobel_出现率')
    lo, hi = [], []
    for ci in d['nobel_CI'].fillna(''):
        m = re.match(r'([\d.]+)—([\d.]+)', str(ci))
        lo.append(float(m.group(1)) if m else np.nan)
        hi.append(float(m.group(2)) if m else np.nan)
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(7.2, 8.4))
    ax.hlines(y, lo, hi, color='#7f8fa6', lw=1.4, alpha=.9)
    ax.plot(d['nobel_出现率'], y, 'o', ms=4.5, color='#2f4f6f', label='诺奖组（含 95%CI）')
    ax.plot(d['cn_出现率'], y, 'D', ms=3.6, color='#c0392b', label='国内组')
    ax.set_yticks(y)
    ax.set_yticklabels(['%s %s' % (i, n) for i, n in zip(d['指标'], d['名称'])], fontsize=7.5)
    ax.set_xlabel('有行为级证据的人数比例（%）', fontsize=9)
    ax.axvline(30, color='#999', ls=':', lw=1)
    ax.axvline(5, color='#999', ls=':', lw=1)
    ax.set_xlim(0, 100)
    ax.legend(fontsize=8, loc='lower right')
    ax.set_title('图 1　29 项指标的行为证据出现率', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig1_observability.png'))
    plt.close(fig)


def fig_scree():
    d = load('10_factorability_nobel')
    obs = d['特征值'].values
    rnd = d['随机95分位'].values
    x = np.arange(1, len(obs) + 1)
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.plot(x, obs, 'o-', color='#2f4f6f', ms=4, label='实际数据特征值')
    ax.plot(x, rnd, 's--', color='#c0392b', ms=3, label='随机数据 95 分位（平行分析）')
    ax.axhline(1, color='#999', ls=':', lw=1)
    ax.set_xlabel('成分序号', fontsize=9)
    ax.set_ylabel('特征值', fontsize=9)
    ax.set_title('图 2　碎石图与平行分析（诺奖组 n=216）', fontsize=10)
    ax.legend(fontsize=8)
    ax.set_xticks(x[::2])
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig2_scree_parallel.png'))
    plt.close(fig)


def fig_cfa_loadings():
    d = load('12_cfa_loadings_nobel')
    col = '六因子（模型原设）'
    rows = []
    for _, r in d.iterrows():
        m = re.search(r'F(\d)=(-?[\d.]+)', str(r[col]))
        if m:
            rows.append((int(r['维度']), r['指标'], int(m.group(1)), float(m.group(2))))
    rows.sort(key=lambda t: (t[0], t[2]))
    labels = ['%s %s' % (dim, ind) for dim, ind, _, _ in rows]
    vals = [v for *_ , v in rows]
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(6.4, 7.6))
    colors = {1: '#2f4f6f', 2: '#3f7f6f', 3: '#8a7f3f', 4: '#7f4f7f', 5: '#8f4f3f', 6: '#3f5f8f'}
    ax.barh(y, vals, color=[colors[d] for d, _, _, _ in rows], height=.7)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.set_xlabel('标准化载荷', fontsize=9)
    ax.axvline(0.3, color='#999', ls=':', lw=1)
    ax.set_xlim(0, .8)
    ax.set_title('图 3　六因子模型的标准化载荷（诺奖组 n=216，颜色＝维度）', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig3_cfa_loadings.png'))
    plt.close(fig)


def fig_composition():
    d = load('07_composition').head(6)
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    w = .38
    ax.bar(x - w / 2, d['国内学生占比%'], w, label='国内学生（n=137）', color='#c0392b')
    ax.bar(x + w / 2, d['诺奖占比%'], w, label='诺奖得主（n=216）', color='#2f4f6f')
    for i, (a, b) in enumerate(zip(d['国内学生占比%'], d['诺奖占比%'])):
        ax.text(i - w / 2, a + 1, '%.1f' % a, ha='center', fontsize=7)
        ax.text(i + w / 2, b + 1, '%.1f' % b, ha='center', fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(['D%d' % i for i in range(1, 7)], fontsize=9)
    ax.set_ylabel('占本组行为证据的百分比（%）', fontsize=9)
    ax.set_ylim(0, 45)
    ax.legend(fontsize=8)
    ax.set_title('图 4　六个维度的构成比（篇幅不可比，只比构成）', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig4_composition.png'))
    plt.close(fig)


def fig_stage_heatmap():
    d = load('06_stage')
    stages = ['中学及以前', '本科', '研究生', '工作后']
    mat, labels = [], []
    for _, r in d.iterrows():
        s = str(r['阶段富集（log2）'])
        if '证据不足' in s or 'nan' in s.lower():
            continue
        vals = []
        for st in stages:
            m = re.search(r'%s (-?[\d.]+)' % re.escape(st), s)
            vals.append(float(m.group(1)) if m else np.nan)
        mat.append(vals)
        labels.append('%s %s' % (r['指标'], r['名称']))
    mat = np.array(mat)
    fig, ax = plt.subplots(figsize=(4.6, 8.2))
    im = ax.imshow(mat, aspect='auto', cmap='RdBu_r', vmin=-3, vmax=3)
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(stages, fontsize=8)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    cb = fig.colorbar(im, ax=ax, fraction=.05, pad=.02)
    cb.set_label('阶段富集 log2(观测/期望)', fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_title('图 5　行为证据的阶段富集（诺奖组）', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig5_stage_heatmap.png'))
    plt.close(fig)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for fn in (fig_observability, fig_scree, fig_cfa_loadings, fig_composition,
               fig_stage_heatmap):
        fn()
        print('已生成', fn.__name__)
    print('输出目录：', OUT)
