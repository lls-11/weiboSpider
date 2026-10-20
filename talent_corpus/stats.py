# -*- coding: UTF-8 -*-
"""分析用的基础统计量，纯 Python 实现，不依赖 scipy。"""

import math


def rankdata(values):
    """平均秩（从 1 开始），并列取平均。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def pearson(x, y):
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(x, y):
    return pearson(rankdata(x), rankdata(y))


def slope(values):
    """values 对 1..n 的最小二乘斜率。"""
    xs = list(range(1, len(values) + 1))
    n = len(values)
    mx, my = sum(xs) / n, sum(values) / n
    sxx = sum((a - mx) ** 2 for a in xs)
    return sum((a - mx) * (b - my) for a, b in zip(xs, values)) / sxx


def normal_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def mann_whitney(a, b):
    """双侧 Mann–Whitney U 检验（正态近似，含并列校正）。返回 (U, p)。"""
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return None, None
    ranks = rankdata(list(a) + list(b))
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    counts = {}
    for v in list(a) + list(b):
        counts[v] = counts.get(v, 0) + 1
    tie = sum(c ** 3 - c for c in counts.values())
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1))) if n > 1 else 0
    if var <= 0:
        return u1, 1.0
    z = (u1 - n1 * n2 / 2) / math.sqrt(var)
    return u1, min(1.0, 2 * normal_sf(abs(z)))


def cliffs_delta(a, b):
    if not a or not b:
        return None
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def two_prop_z(k1, n1, k2, n2):
    if n1 == 0 or n2 == 0:
        return None
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k1 / n1 - k2 / n2) / se
    return 2 * normal_sf(abs(z))


def cohen_kappa(a, b, weights=None, categories=None):
    """Cohen's kappa；weights='quadratic' 时为加权 kappa（有序类别）。"""
    if not a or len(a) != len(b):
        return None
    cats = sorted(set(a) | set(b)) if categories is None else list(categories)
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    if k < 2:
        return None
    n = len(a)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1 / n
    ra = [sum(row) for row in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    def w(i, j):
        if weights == 'quadratic':
            return ((i - j) / (k - 1)) ** 2
        return 0.0 if i == j else 1.0

    do = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    de = sum(w(i, j) * ra[i] * cb[j] for i in range(k) for j in range(k))
    if de == 0:
        return 1.0 if do == 0 else None
    return 1 - do / de


def median(values):
    v = sorted(values)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
