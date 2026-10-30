# -*- coding: UTF-8 -*-
"""因素分析的最小实现：平行分析、主轴因子法（EFA）、ML 验证性因素分析（CFA）、McDonald ω。

只依赖 numpy / scipy，参数与判读标准都写在函数里，便于逐行核对。样本较小时
（本项目诺奖组 n=216、国内组 n=137）报告 CFA 结果必须同时说明拟合指标与样本量，
不宜把拟合优度当作模型成立的证据。

术语提醒：指标是二分变量（有行为证据 / 无），严格做法是先用四分相关（tetrachoric）
或直接用 WLSMV 估计；这里主分析用 Pearson（φ）相关 + ML，并报告 tetrachoric 相关下的
平行分析结果作敏感性检验，两者的因子数若一致，结论更稳。
"""

import numpy as np
from scipy import optimize, stats


# ---------------------------------------------------------------- 相关矩阵

def tetrachoric(R, counts):
    """用 2×2 表的近似公式把 φ 相关换成四分相关（Bonett & Price, 2005）。

    cos(pi / (1 + sqrt(OR)))，其中 OR 由 φ 与边际比例换算。只用于敏感性检验。
    """
    out = R.copy()
    p = R.shape[0]
    for i in range(p):
        for j in range(p):
            if i == j:
                continue
            r = float(np.clip(R[i, j], -0.999, 0.999))
            pi_, pj = counts[i], counts[j]
            # φ 与优势比的关系：φ = (a - pi_*pj)/sqrt(pi_*(1-pi_)*pj*(1-pj))
            a = r * np.sqrt(pi_ * (1 - pi_) * pj * (1 - pj)) + pi_ * pj
            b, c = pi_ - a, pj - a
            d = 1 - a - b - c
            if min(a, b, c, d) <= 0:
                out[i, j] = r
                continue
            out[i, j] = np.cos(np.pi / (1 + np.sqrt((a * d) / (b * c))))
    return (out + out.T) / 2


# ---------------------------------------------------------------- 平行分析

def parallel_analysis(R, n_obs, n_iter=300, seed=20261030, quantile=95):
    """Horn 平行分析：观测特征值 vs 同规模随机数据特征值的分位数。

    保留“观测特征值 > 随机分位”的成分个数，作为因子数的上限参考。
    """
    p = R.shape[0]
    obs = np.sort(np.linalg.eigvalsh(R))[::-1]
    rng = np.random.default_rng(seed)
    sims = np.empty((n_iter, p))
    for i in range(n_iter):
        X = rng.standard_normal((n_obs, p))
        sims[i] = np.sort(np.linalg.eigvalsh(np.corrcoef(X, rowvar=False)))[::-1]
    return obs, np.percentile(sims, quantile, axis=0)


def n_factors_by_pa(obs, rand):
    """观测特征值超过随机分位的个数（至少 1）。"""
    keep = int(np.sum(obs > rand))
    return max(keep, 1)


# ---------------------------------------------------------------- EFA

def varimax(load, iters=300, tol=1e-8):
    """方差极大旋转（Kaiser 归一化后迭代）。"""
    p, k = load.shape
    if k < 2:
        return load
    h = np.sqrt((load ** 2).sum(axis=1))
    h[h == 0] = 1
    L = load / h[:, None]
    r = np.eye(k)
    d_old = 0
    for _ in range(iters):
        Lr = L @ r
        u, s, vt = np.linalg.svd(
            L.T @ (Lr ** 3 - Lr @ np.diag((Lr ** 2).sum(axis=0)) / p))
        r = u @ vt
        d = s.sum()
        if d_old and d / d_old < 1 + tol:
            break
        d_old = d
    return (L @ r) * h[:, None]


def paf(R, k, iters=500, tol=1e-7):
    """主轴因子法：反复用共同度替换对角线，取前 k 个特征值/向量。"""
    p = R.shape[0]
    try:
        h2 = 1 - 1 / np.diag(np.linalg.inv(R))
    except np.linalg.LinAlgError:
        h2 = np.full(p, 0.4)
    h2 = np.clip(h2, 0.01, 0.99)
    load = np.zeros((p, k))
    for _ in range(iters):
        Rs = R.copy()
        np.fill_diagonal(Rs, h2)
        w, v = np.linalg.eigh(Rs)
        idx = np.argsort(w)[::-1][:k]
        load = v[:, idx] * np.sqrt(np.clip(w[idx], 0, None))
        new = np.clip((load ** 2).sum(axis=1), 1e-3, 0.999)
        if np.max(np.abs(new - h2)) < tol:
            h2 = new
            break
        h2 = new
    return varimax(load), h2


# ---------------------------------------------------------------- CFA

def build_pattern(pairs, p):
    """pairs: [(指标下标, 因子下标)] → (载荷矩阵模板, 单指标因子集合)。"""
    k = max(f for _, f in pairs) + 1
    pat = np.zeros((p, k), dtype=int)
    for i, f in pairs:
        pat[i, f] = 1
    single = {i for i in range(p) if pat[i].sum() == 1 and pat[:, pat[i].argmax()].sum() == 1}
    return pat, k, single


def cfa_ml(S, pairs, n, maxiter=4000):
    """ML 验证性因素分析。

    设定：因子方差固定为 1；载荷自由（单指标因子载荷固定 1、残差固定 0）；
    残差方差自由且互相独立；因子间相关自由估计。
    返回 dict：chi2, df, p, CFI, TLI, RMSEA, SRMR, AIC, BIC, loadings_std, phi。
    """
    p = S.shape[0]
    pat, k, single = build_pattern(pairs, p)
    load_idx = [(i, f) for i in range(p) for f in range(k) if pat[i, f] and i not in single]
    res_idx = [i for i in range(p) if i not in single]
    n_phi = k * (k - 1) // 2
    n_par = len(load_idx) + len(res_idx) + n_phi

    def unpack(theta):
        L = np.zeros((p, k))
        for f in range(k):
            for i in range(p):
                if pat[i, f] and i in single:
                    L[i, f] = 1.0
        j = 0
        for i, f in load_idx:
            L[i, f] = theta[j]
            j += 1
        res = np.zeros(p)
        for i in res_idx:
            res[i] = max(theta[j], 1e-4)
            j += 1
        Phi = np.eye(k)
        for a in range(k):
            for b in range(a + 1, k):
                Phi[a, b] = Phi[b, a] = theta[j]
                j += 1
        return L, res, Phi

    logdet_S = np.linalg.slogdet(S)[1]

    def fit(theta):
        L, res, Phi = unpack(theta)
        Sigma = L @ Phi @ L.T + np.diag(res)
        sign, logdet = np.linalg.slogdet(Sigma)
        if sign <= 0:
            return 1e6
        try:
            inv = np.linalg.inv(Sigma)
        except np.linalg.LinAlgError:
            return 1e6
        return logdet + float(np.trace(S @ inv)) - logdet_S - p

    x0 = np.concatenate([[0.5] * len(load_idx), [0.5] * len(res_idx),
                         [0.3] * n_phi])
    bounds = [(-0.95, 0.95)] * len(load_idx) + [(1e-3, 3.0)] * len(res_idx) + \
             [(-0.95, 0.95)] * n_phi
    best = None
    for start in (x0, x0 * 0.6 + 0.2):
        try:
            r = optimize.minimize(fit, start, method='L-BFGS-B', bounds=bounds,
                                  options={'maxiter': maxiter})
            if best is None or r.fun < best.fun:
                best = r
        except Exception:
            continue
    if best is None:
        raise RuntimeError('CFA 优化失败')
    L, res, Phi = unpack(best.x)
    Sigma = L @ Phi @ L.T + np.diag(res)
    chi2 = (n - 1) * fit(best.x)
    df = p * (p + 1) // 2 - n_par
    df = max(df, 1)
    # 独立模型（对角）
    F_null = float(np.sum(np.log(np.diag(S))) - logdet_S)
    chi2_null = (n - 1) * F_null
    df_null = p * (p + 1) // 2 - p
    cfi = 1 - max(chi2 - df, 0) / max(chi2_null - df_null, 1e-9)
    tli = ((chi2_null / df_null) - (chi2 / df)) / ((chi2_null / df_null) - 1)
    rmsea = float(np.sqrt(max((chi2 - df) / (df * (n - 1)), 0)))
    d = np.sqrt(np.diag(S))
    resid = (S - Sigma) / np.outer(d, d)
    iu = np.triu_indices(p, 1)
    srmr = float(np.sqrt(np.mean(resid[iu] ** 2)))
    sd = np.sqrt(np.diag(Sigma))
    std_load = L / sd[:, None]
    return {'chi2': float(chi2), 'df': int(df),
            'p': float(stats.chi2.sf(chi2, df)),
            'CFI': float(cfi), 'TLI': float(tli), 'RMSEA': rmsea, 'SRMR': srmr,
            'AIC': float(chi2 + 2 * n_par), 'BIC': float(chi2 + np.log(n) * n_par),
            'n_par': int(n_par), 'loadings_std': std_load, 'phi': Phi,
            'loadings': L, 'resid': res}


def omega(load):
    """McDonald ω：按因子分别计算，只统计该因子上的指标（载荷为 0 的不计入误差项）。"""
    load = np.asarray(load, dtype=float)
    out = []
    for f in range(load.shape[1]):
        l = load[:, f]
        l = l[np.abs(l) > 1e-8]
        if l.size == 0:
            out.append(float('nan'))
            continue
        ss = float(l.sum()) ** 2
        err = float((1 - l ** 2).sum())
        out.append(ss / (ss + err))
    return np.array(out)


def dimension_pairs(codes_dim, codes_ids):
    """把“指标→维度”映射转成 CFA 的 (指标下标, 因子下标) 列表。"""
    idx = {c: i for i, c in enumerate(codes_ids)}
    return [(idx[c], codes_dim[c] - 1) for c in codes_ids]
