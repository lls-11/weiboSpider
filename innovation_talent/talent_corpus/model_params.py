# -*- coding: UTF-8 -*-
"""创新人才识别模型（TAD 四阶段版 v0.2）的默认参数与权重计算。

参数与《创新人才识别模型》网页、Excel《参数》《指标权重》表一致，
公式见框架文档第六章：
    指标原始分量 = 证据系数 × 阶段相关度(t) × 调整倍数
    类内占比     = 原始分量 ÷ 同类原始分量之和
    指标总权重   = 类别权重(t) × 类内占比
"""

STAGES = ['潜能倾向', '领域胜任能力', '专长', '原创贡献拓展']

DIMS = {
    1: '自主方向与价值认同',
    2: '好奇与主动探索',
    3: '信息接纳与过滤',
    4: '联结与问题重构',
    5: '独立判断与认知调节',
    6: '自主投入与迭代实现',
}

# 类别 × 阶段 相对权重（行：类别 1–6；列：阶段 1–4）
DEF_DM = [
    [10, 15, 18, 22],
    [28, 20, 14, 12],
    [20, 12, 8, 6],
    [20, 22, 20, 18],
    [8, 14, 20, 20],
    [14, 17, 20, 22],
]

GRADE_COEF = {'A': 1.0, 'B': 0.6, 'C': 0.3}

# (编号, 类别, 指标, 证据等级, 阶段相关度 s1..s4)
INDICATORS = [
    ('C01', 1, '目标清晰度', 'C', (.4, .8, 1, 1)),
    ('C02', 1, '目标自我一致性', 'B', (.6, .9, 1, 1)),
    ('C03', 1, '自主性动机', 'A', (1, 1, .9, .9)),
    ('C04', 1, '领域身份认同', 'B', (.3, 1, 1, .8)),
    ('C05', 1, '目标与实际选择一致性', 'C', (.2, .7, 1, 1)),
    ('C06', 2, '求知好奇心', 'A', (1, .8, .6, .6)),
    ('C07', 2, '知识缺口敏感性', 'B', (.8, 1, 1, .9)),
    ('C08', 2, '自发提问', 'B', (1, .8, .6, .5)),
    ('C09', 2, '问题新颖性', 'A', (.8, .9, 1, 1)),
    ('C10', 2, '主动信息搜寻', 'A', (1, 1, .8, .6)),
    ('C11', 2, '对兴趣的反复返回', 'C', (1, .8, .5, .4)),
    ('C12', 3, '潜伏抑制', 'A', (1, .8, .6, .6)),
    ('C13', 3, '注意范围', 'C', (1, .7, .5, .4)),
    ('C14', 3, '边缘线索利用', 'C', (.8, .9, 1, 1)),
    ('C15', 3, '干扰下的信息筛选', 'C', (.6, 1, 1, .8)),
    ('C16', 4, '远距离联结', 'A', (1, .9, .8, .8)),
    ('C17', 4, '语义网络结构', 'B', (.9, 1, .8, .6)),
    ('C18', 4, '跨领域类比', 'B', (.4, .7, 1, 1)),
    ('C19', 4, '问题重新表征', 'A', (.6, .9, 1, 1)),
    ('C20', 4, '突破定势', 'B', (.8, .9, 1, 1)),
    ('C21', 4, '隐藏规律发现', 'B', (1, .8, .6, .5)),
    ('C22', 4, '休息后的顿悟增益', 'C', (.8, .8, .7, .6)),
    ('C23', 5, '创意评价准确性', 'A', (.5, .9, 1, 1)),
    ('C24', 5, '生成与评价的调节', 'C', (.3, .7, 1, 1)),
    ('C25', 5, '抵抗无依据的多数压力', 'C', (.5, .7, .9, 1)),
    ('C26', 5, '根据反证更新判断', 'C', (.4, .8, 1, 1)),
    ('C27', 5, '利用异议扩展策略', 'B', (.4, .8, 1, .9)),
    ('C28', 6, '自发项目', 'B', (.6, .8, 1, 1)),
    ('C29', 6, '持续投入', 'B', (.5, 1, 1, .9)),
    ('C30', 6, '失败后重新投入', 'C', (.4, .8, 1, 1)),
    ('C31', 6, '策略调整', 'B', (.4, .8, 1, .9)),
    ('C32', 6, '作品修改增益', 'C', (.3, .8, 1, .9)),
    ('C33', 6, '想法转化为可检验方案', 'C', (.2, .6, 1, 1)),
]

IND_BY_ID = {i[0]: i for i in INDICATORS}


def lerp(values, t):
    """在 1–4 的阶段轴上线性插值，与网页模型的 lerp 一致。"""
    x = min(max(t, 1), 4) - 1
    i = min(int(x), 2)
    f = x - i
    return values[i] * (1 - f) + values[i + 1] * f


def dim_shares(t, dm=None):
    dm = dm or DEF_DM
    raw = [max(0, lerp(row, t)) for row in dm]
    total = sum(raw) or 1
    return {k: raw[k - 1] / total for k in DIMS}


def indicator_weights(t, dm=None, grade=None, mult=None, include_c=True,
                      only=None):
    """返回 {指标编号: (类内占比, 总权重)}。

    only 为可选的指标编号集合：不在集合内的指标权重记为 0，
    其余指标在类别内重新归一化（例如只保留文本可观测的指标）。
    """
    grade = grade or GRADE_COEF
    mult = mult or {}
    shares = dim_shares(t, dm)
    raw = {}
    for iid, dim, _, g, rel in INDICATORS:
        if (not include_c and g == 'C') or (only is not None and iid not in only):
            raw[iid] = 0.0
        else:
            raw[iid] = grade[g] * lerp(rel, t) * mult.get(iid, 1)
    out = {}
    for dim in DIMS:
        ids = [i[0] for i in INDICATORS if i[1] == dim]
        tot = sum(raw[i] for i in ids)
        for i in ids:
            within = raw[i] / tot if tot else 0.0
            out[i] = (within, within * shares[dim])
    return out


def evaluate(scores, t, **kwargs):
    """按模型规则计算类别得分、综合参考分与覆盖率。

    scores: {指标编号: 0–100 分或 None}；缺测不记零分，
    权重在同类已测指标之间重新分配。
    """
    w = indicator_weights(t, **kwargs)
    shares = dim_shares(t, kwargs.get('dm'))
    dims = {}
    for dim in DIMS:
        ids = [i[0] for i in INDICATORS if i[1] == dim]
        tw = aw = s = 0.0
        for i in ids:
            within = w[i][0]
            tw += within
            if scores.get(i) is not None and within > 0:
                aw += within
                s += within * scores[i]
        dims[dim] = {'score': s / aw if aw else None,
                     'coverage': aw / tw if tw else 0.0}
    cw = cs = cov = 0.0
    for dim, r in dims.items():
        cov += shares[dim] * r['coverage']
        if r['score'] is not None:
            cw += shares[dim]
            cs += shares[dim] * r['score']
    return {'dims': dims, 'composite': cs / cw if cw else None,
            'coverage': cov}
