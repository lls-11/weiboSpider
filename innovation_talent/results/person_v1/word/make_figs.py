# -*- coding: UTF-8 -*-
"""为 Word 报告画图：python results/person_v1/word/make_figs.py（innovation_talent 目录下）"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', 'dashboard')
OUT = os.path.join(HERE, 'figs')
os.makedirs(OUT, exist_ok=True)
for f in font_manager.findSystemFonts():
    if 'wqy-zenhei' in f.lower() or 'wenquanyi' in f.lower():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({'font.family': ['WenQuanYi Zen Hei'], 'font.size': 9, 'axes.unicode_minus': False,
                     'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#8a8f98',
                     'axes.labelcolor': '#333', 'xtick.color': '#555', 'ytick.color': '#333'})
CN, NB, M2, M4 = '#2f6f9f', '#d07a2c', '#9fb7c9', '#7a5c99'
LIFE = ['中学及以前', '本科', '研究生', '工作后']
I = pd.read_csv(os.path.join(D, 'indicators.csv'))
lab = I.id + ' ' + I.name


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=220, bbox_inches='tight')
    plt.close(fig)


# 1 观测率
d = I.assign(lab=lab).sort_values('nobel_beh')
fig, ax = plt.subplots(figsize=(6.3, 7.4))
y = np.arange(len(d))
ax.hlines(y, d[['cn_beh', 'nobel_beh']].min(axis=1), d[['cn_beh', 'nobel_beh']].max(axis=1), color='#c8ccd2', lw=2)
ax.scatter(d.cn_beh, y, color=CN, s=26, label='国内学生', zorder=3)
ax.scatter(d.nobel_beh, y, color=NB, s=26, label='诺奖得主', zorder=3)
ax.set_yticks(y, d.lab)
ax.set_xlim(0, 1)
ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
ax.grid(axis='x', color='#e5e7ea')
ax.set_xlabel('有具体行为证据的人数占比')
ax.legend(loc='lower right', frameon=False)
save(fig, 'fig1_prevalence.png')

# 2 声明比例
d = I.assign(lab=lab, a=I.cn_stmt_share.fillna(0), b=I.nobel_stmt_share.fillna(0))
d = d[d[['a', 'b']].max(axis=1) >= 0.1].sort_values('b')
fig, ax = plt.subplots(figsize=(6.3, 2.9))
y = np.arange(len(d))
ax.barh(y + 0.2, d.a, 0.38, color=CN, label='国内学生')
ax.barh(y - 0.2, d.b, 0.38, color=NB, label='诺奖得主')
ax.set_yticks(y, d.lab)
ax.set_xlim(0, 1)
ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
ax.set_xlabel('该指标的判断中“只有声明”的比例')
ax.legend(loc='lower right', frameon=False)
ax.grid(axis='x', color='#e5e7ea')
save(fig, 'fig2_statement.png')

# 3 类别构成与模型权重
m = pd.read_csv(os.path.join(D, 'dimensions.csv'))
fig, ax = plt.subplots(figsize=(6.3, 3.4))
x = np.arange(len(m))
w = 0.2
for k, (col, c, n) in enumerate([('cn_share', CN, '国内学生'), ('nobel_share', NB, '诺奖得主'),
                                 ('model_s2', M2, '模型权重·阶段 2'), ('model_s4', M4, '模型权重·阶段 4')]):
    ax.bar(x + (k - 1.5) * w, m[col], w, color=c, label=n)
ax.set_xticks(x, [f'{a} {b[:4]}\n{b[4:]}' for a, b in zip(m.dim, m.dim_name)], fontsize=8)
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
ax.set_ylabel('占全部行为证据 / 权重的比例')
ax.legend(ncol=4, frameon=False, loc='upper center', bbox_to_anchor=(0.5, 1.12))
ax.grid(axis='y', color='#e5e7ea')
save(fig, 'fig3_composition.png')

# 4 偏相关热图
pr = pd.read_csv(os.path.join(D, 'partial_r.csv'))
ids = list(I.id)
R = pd.DataFrame(np.nan, index=ids, columns=ids)
for a, b, r in pr.itertuples(index=False):
    R.loc[a, b] = r
fig, ax = plt.subplots(figsize=(6.3, 5.9))
im = ax.imshow(R.values.astype(float), cmap='RdBu_r', vmin=-0.35, vmax=0.35)
ax.set_xticks(range(len(ids)), [i[1:] for i in ids], fontsize=7, rotation=90)
ax.set_yticks(range(len(ids)), [i[1:] for i in ids], fontsize=7)
ax.spines[:].set_visible(False)
dims = I.dim.values
start = 0
for k in range(1, len(ids) + 1):
    if k == len(ids) or dims[k] != dims[start]:
        ax.add_patch(plt.Rectangle((start - 0.5, start - 0.5), k - start, k - start, fill=False, ec='#222', lw=1.1))
        start = k
fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label='偏相关 r（控制篇幅）')
save(fig, 'fig4_structure.png')

# 5 阶段富集
E = I[['enrich_s1', 'enrich_s2', 'enrich_s3', 'enrich_s4']].values.astype(float)
L = np.log2(np.where(E > 0, E, np.nan))
fig, ax = plt.subplots(figsize=(6.3, 7.6))
im = ax.imshow(np.clip(L, -2, 2), cmap='PuOr_r', vmin=-2, vmax=2, aspect='auto')
ax.set_xticks(range(4), LIFE)
ax.set_yticks(range(len(I)), lab)
ax.xaxis.tick_top()
ax.spines[:].set_visible(False)
for i, (pk, tag, n) in enumerate(zip(I.prior_peak, I.trend_agree, I.stage_n)):
    if pk in LIFE:
        j = LIFE.index(pk)
        ax.add_patch(plt.Rectangle((j - 0.48, i - 0.46), 0.96, 0.92, fill=False, ec='#111', lw=1.3))
    color = {'一致': '#2e7d32', '相反': '#c62828'}.get(tag, '#888')
    ax.text(3.65, i, '—' if tag == '不判断' else tag, va='center', color=color, fontsize=8)
    if n < 20:
        for j in range(4):
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fc='white', alpha=0.55, ec='none'))
ax.text(3.65, -1.1, '与先验', fontsize=8, color='#555')
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.12, orientation='horizontal')
cb.set_label('log2 富集（> 0 偏向该阶段）；框线为模型先验最高的阶段；浅色为证据不足 20 条')
save(fig, 'fig5_stage.png')

# 6 研究生与本科生
e = pd.read_csv(os.path.join(D, 'education.csv'))
fig, ax = plt.subplots(figsize=(6.3, 2.6))
y = np.arange(len(e))[::-1]
for yy, r in zip(y, e.itertuples()):
    c = CN if r.p < 0.05 else '#a0a6ad'
    ax.plot([r.lo, r.hi], [yy, yy], color=c, lw=2, solid_capstyle='round')
    ax.scatter(r.irr, yy, color=c, s=30, zorder=3)
    ax.text(5.2, yy, f'{r.irr:.2f}（{r.lo:.2f}–{r.hi:.2f}）  p = {r.p:.3f}', va='center', fontsize=8)
ax.axvline(1, color='#666', ls='--', lw=1)
ax.set_xscale('log')
ax.set_xlim(0.03, 5)
ax.set_xticks([0.05, 0.1, 0.25, 0.5, 1, 2, 4], ['0.05', '0.1', '0.25', '0.5', '1', '2', '4'])
ax.set_yticks(y, [f'{a} {b}' for a, b in zip(e.dim, e.dim_name)])
ax.set_xlabel('研究生 / 本科生 行为证据发生率比（对数刻度，控制篇幅）')
save(fig, 'fig6_education.png')
print(sorted(os.listdir(OUT)))
