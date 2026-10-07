"""Difference-in-differences with one treated unit.

With one treated region and a balanced panel, the two-way fixed-effects DiD
coefficient equals a regression of the gap series
    d_t = y_treated,t - mean(y_donors,t)
on a post-period dummy. Working on d_t makes the assumptions visible and lets
us use Newey-West (HAC) standard errors for serial correlation. Cluster-robust
errors are not usable with four regions.
"""
from __future__ import annotations
import numpy as np, pandas as pd, statsmodels.api as sm
from .data import qnum, qstr


def gap_series(w: pd.DataFrame, treated: str, donors: list[str], weights=None) -> pd.Series:
    wts = np.full(len(donors), 1 / len(donors)) if weights is None else np.asarray(weights)
    return w[treated] - w[donors].to_numpy() @ wts


def did(w, treated, donors, event_q, pre_start, post_n, trend=False, seasonal=False,
        drop=(), weights=None, hac_lags=2) -> dict:
    """tau = average post-period change in the gap. Units are those of the outcome."""
    d = gap_series(w, treated, donors, weights).dropna()
    t = np.array([qnum(q) for q in d.index])
    e = qnum(event_q)
    keep = (t >= qnum(pre_start)) & (t < e + post_n) & ~np.isin(d.index, list(drop))
    d, t = d[keep], t[keep]
    post = (t >= e).astype(float)
    X = {"const": np.ones(len(d)), "post": post}
    if trend:      # region-specific linear trend in the gap
        X["trend"] = (t - e).astype(float)
    if seasonal:   # region-specific seasonality in the gap
        for k in (1, 2, 3):
            X[f"q{k+1}"] = (t % 4 == k).astype(float)
    X = pd.DataFrame(X, index=d.index)
    fit = sm.OLS(d, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags, "use_correction": True})
    tau, se = float(fit.params["post"]), float(fit.bse["post"])
    return {"tau": tau, "se": se, "ci_low": tau - 1.96 * se, "ci_high": tau + 1.96 * se,
            "p_value": float(fit.pvalues["post"]), "n_pre": int((post == 0).sum()),
            "n_post": int(post.sum()), "pre_gap_mean": float(d[post == 0].mean()),
            "post_gap_mean": float(d[post == 1].mean())}


def event_study(w, treated, donors, event_q, pre_start, post_n, trend=False) -> pd.DataFrame:
    """Gap by quarter relative to the pre-period fit (mean, or linear trend)."""
    d = gap_series(w, treated, donors).dropna()
    t = np.array([qnum(q) for q in d.index]); e = qnum(event_q)
    keep = (t >= qnum(pre_start)) & (t < e + post_n)
    d, t = d[keep], t[keep]
    pre = t < e
    if trend:
        b = np.polyfit(t[pre] - e, d[pre], 1); base = np.polyval(b, t - e)
    else:
        base = np.full(len(d), d[pre].mean())
    return pd.DataFrame({"quarter": d.index, "rel": t - e, "gap": d.values, "effect": d.values - base})


def placebo_in_time(w, treated, donors, event_q, pre_start, post_n, min_pre=6, **kw) -> dict:
    """Re-run the DiD at fake event dates that lie wholly before the real event."""
    e, s = qnum(event_q), qnum(pre_start)
    taus = []
    for fake in range(s + min_pre, e - post_n + 1):
        r = did(w.loc[[q for q in w.index if qnum(q) < e]], treated, donors, qstr(fake), pre_start, post_n, **kw)
        taus.append((qstr(fake), r["tau"]))
    real = did(w, treated, donors, event_q, pre_start, post_n, **kw)["tau"]
    vals = np.array([x[1] for x in taus])
    p = float((1 + (np.abs(vals) >= abs(real)).sum()) / (1 + len(vals)))
    return {"placebo_taus": taus, "p_value": p, "placebo_sd": float(vals.std(ddof=1)) if len(vals) > 1 else None}
