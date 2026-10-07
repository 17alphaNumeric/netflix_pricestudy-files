"""Synthetic control for one treated region and a small donor pool.

Two estimators:

* `scaled_synth` (primary). Counterfactual = intercept + sum_j w_j * donor_j with
  w_j >= 0 and NO adding-up constraint (Doudchenko & Imbens 2016). Classic
  synthetic control needs the treated unit inside the convex hull of the
  donors. UCAN is the slowest-growing region every year and a mature market
  absorbs common shocks at a fraction of the size seen elsewhere, so the
  weights must be allowed to sum to less than one.
* `demeaned_synth` (robustness). Weights >= 0 that sum to one after removing
  pre-period means (Ferman & Pinto 2021). This is DiD with data-driven weights.

Inference uses leave-one-out pre-period residuals and a moving-block
permutation, in the spirit of Chernozhukov, Wuthrich & Zhu (2021).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy.optimize import nnls, minimize
from .data import qnum, qstr


def _fit_scaled(y: np.ndarray, X: np.ndarray):
    A = np.c_[np.ones(len(y)), -np.ones(len(y)), X]      # +/- columns give a free-sign intercept
    b, _ = nnls(A, y)
    return b[0] - b[1], b[2:]


def _block_means(res: np.ndarray, n: int) -> np.ndarray:
    return np.array([res[i:i + n].mean() for i in range(len(res) - n + 1)])


def scaled_synth(w: pd.DataFrame, treated: str, donors: list[str], event_q: str,
                 pre_start: str | None = None, post_n: int | None = None, drop=()) -> dict:
    x = w[[treated] + donors].dropna()
    t = np.array([qnum(q) for q in x.index]); e = qnum(event_q)
    keep = np.ones(len(x), bool) if pre_start is None else t >= qnum(pre_start)
    if post_n is not None:
        keep &= t < e + post_n
    x, t = x[keep], t[keep]
    pre = (t < e) & ~np.isin(x.index, list(drop))
    post = t >= e
    y, X = x[treated].to_numpy(), x[donors].to_numpy()
    b0, wts = _fit_scaled(y[pre], X[pre])
    cf = b0 + X @ wts
    gap = y - cf
    # leave-one-out residuals: honest measure of pre-period forecast error
    idx = np.where(pre)[0]
    loo = np.array([y[i] - (lambda f: f[0] + X[i] @ f[1])(_fit_scaled(y[idx[idx != i]], X[idx[idx != i]]))
                    for i in idx])
    out = {"intercept": float(b0), "weights": dict(zip(donors, [float(v) for v in wts])),
           "quarters": list(x.index), "actual": y.tolist(), "counterfactual": cf.tolist(),
           "gap": gap.tolist(), "pre_mask": pre.tolist(), "post_mask": post.tolist(),
           "rmse_pre": float(np.sqrt((gap[pre] ** 2).mean())),
           "rmse_loo": float(np.sqrt((loo ** 2).mean())), "loo_residuals": loo.tolist(),
           "n_pre": int(pre.sum())}
    if post.any():
        g = gap[post]; n = len(g)
        blocks = _block_means(loo, n)
        se = float(np.sqrt((blocks ** 2).mean()))        # RMS of placebo block means
        tau = float(g.mean())
        out.update(tau=tau, se=se, ci_low=tau - 1.96 * se, ci_high=tau + 1.96 * se,
                   cumulative=float(g.sum()), cumulative_se=se * n,
                   p_value=float((1 + (np.abs(blocks) >= abs(tau)).sum()) / (1 + len(blocks))),
                   post_quarters=[q for q, m in zip(x.index, post) if m], post_gap=g.tolist(),
                   rmspe_ratio=float(np.sqrt((g ** 2).mean()) / out["rmse_loo"]))
    return out


def window_effect(fit: dict, k: int) -> dict:
    """Cumulative effect over the first k post quarters, with a block-permutation SE."""
    g = np.array(fit["post_gap"][:k]); loo = np.array(fit["loo_residuals"])
    blocks = _block_means(loo, k) * k
    se = float(np.sqrt((blocks ** 2).mean()))
    c = float(g.sum())
    return {"quarters": fit["post_quarters"][:k], "cumulative": c, "se": se,
            "ci_low": c - 1.96 * se, "ci_high": c + 1.96 * se,
            "p_value": float((1 + (np.abs(blocks) >= abs(c)).sum()) / (1 + len(blocks)))}


def demeaned_synth(w, treated, donors, event_q, pre_start=None, post_n=None) -> dict:
    x = w[[treated] + donors].dropna()
    t = np.array([qnum(q) for q in x.index]); e = qnum(event_q)
    keep = np.ones(len(x), bool) if pre_start is None else t >= qnum(pre_start)
    if post_n is not None:
        keep &= t < e + post_n
    x, t = x[keep], t[keep]; pre = t < e
    xd = x - x[pre].mean()
    y, X = xd.loc[pre, treated].to_numpy(), xd.loc[pre, donors].to_numpy()
    k = len(donors)
    res = minimize(lambda v: float(((y - X @ v) ** 2).sum()), np.full(k, 1 / k), method="SLSQP",
                   bounds=[(0, 1)] * k, constraints={"type": "eq", "fun": lambda v: v.sum() - 1})
    wts = np.clip(res.x, 0, 1); wts /= wts.sum()
    gap = xd[treated].to_numpy() - xd[donors].to_numpy() @ wts
    return {"weights": dict(zip(donors, [float(v) for v in wts])),
            "rmse_pre": float(np.sqrt((gap[pre] ** 2).mean())), "tau": float(gap[~pre].mean())}


def placebo_in_space(w, treated, donors, event_q, pre_start, post_n) -> dict:
    """Pretend each donor was treated, with the other donors as its pool. With
    3 donors the smallest attainable p-value is 1/4: a rank check, not a test."""
    rows = {treated: scaled_synth(w, treated, donors, event_q, pre_start, post_n)}
    for d in donors:
        rows[d] = scaled_synth(w, d, [x for x in donors if x != d], event_q, pre_start, post_n)
    ratios = {k: v["rmspe_ratio"] for k, v in rows.items()}
    r = np.array(list(ratios.values()))
    return {"by_unit": {k: {"tau": v["tau"], "rmspe_ratio": v["rmspe_ratio"]} for k, v in rows.items()},
            "rank_of_treated": int((r >= ratios[treated]).sum()), "n_units": len(rows),
            "p_value": float((r >= ratios[treated]).mean())}


def placebo_in_time(w, treated, donors, event_q, pre_start, post_n, min_pre=8) -> dict:
    """Fit on data before a fake event date and measure the 'effect' in the next
    post_n quarters, all of which lie before the real event."""
    e = qnum(event_q)
    first = qnum(pre_start or w[[treated] + donors].dropna().index[0])
    ww = w.loc[[q for q in w.index if qnum(q) < e]]
    rows = []
    for fake in range(first + min_pre, e - post_n + 1):
        r = scaled_synth(ww, treated, donors, qstr(fake), pre_start, post_n)
        rows.append({"fake_event": qstr(fake), "tau": r["tau"]})
    return {"placebos": rows}


def leave_one_out_donors(w, treated, donors, event_q, pre_start, post_n) -> dict:
    return {d: scaled_synth(w, treated, [x for x in donors if x != d], event_q, pre_start, post_n)["tau"]
            for d in donors}
