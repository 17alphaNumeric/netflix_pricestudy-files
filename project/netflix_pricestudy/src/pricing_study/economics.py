"""Price change, elasticity and counterfactual revenue."""
from __future__ import annotations
import numpy as np, pandas as pd
from .data import ROOT, qnum
from .synth import window_effect


def list_price_change(event_id="ucan_2022") -> dict:
    e = pd.read_csv(ROOT / "data/raw/price_events.csv").query("event_id == @event_id")
    pct = {r.plan: 100 * (r.new_price_usd / r.old_price_usd - 1) for r in e.itertuples()}
    return {"by_plan_pct": pct, "simple_mean_pct": float(np.mean(list(pct.values())))}


def arm_change(panel: pd.DataFrame, region: str, base_q: str, post_qs: list[str]) -> dict:
    a = panel[panel.region == region].set_index("quarter")["arm_usd"]
    post_qs = [q for q in post_qs if q in a.index and not np.isnan(a[q])]
    after = float(a[post_qs].mean())
    return {"arm_before": float(a[base_q]), "arm_after": after,
            "pct": 100 * (after / a[base_q] - 1), "log_pct": 100 * float(np.log(after / a[base_q]))}


def elasticity(fit: dict, arm_pct: float) -> dict:
    """Arc elasticity of paid memberships with respect to realised price (ARM).
    Quantity effect = cumulative gap in membership growth, which is the % gap in
    the membership base versus the counterfactual. The price change is treated
    as known, so the interval reflects uncertainty in the quantity effect only."""
    out = {}
    for name, k in (("first_2_quarters", 2), ("first_4_quarters", 4)):
        if len(fit["post_gap"]) < k:
            continue
        w = window_effect(fit, k)
        out[name] = {"quantity_effect_pct": w["cumulative"], "price_change_pct": arm_pct,
                     "elasticity": w["cumulative"] / arm_pct, "ci_low": w["ci_low"] / arm_pct,
                     "ci_high": w["ci_high"] / arm_pct, "p_value": w["p_value"]}
    return out


def revenue_counterfactual(panel, fit, region, base_q, arm_cf_growth_q=0.0, shift=0.0) -> pd.DataFrame:
    """Quarterly actual vs no-price-change revenue ($M).

    Counterfactual memberships compound the synthetic growth path from the
    actual base. Counterfactual ARM is held at its pre-change level (or grows
    at `arm_cf_growth_q` per quarter). `shift` adds pp to counterfactual growth
    each quarter and is used to trace out the confidence band."""
    p = panel[panel.region == region].set_index("quarter")
    post = fit["post_quarters"]
    cf_g = dict(zip(fit["quarters"], fit["counterfactual"]))
    m_prev_cf = m_prev = float(p.loc[base_q, "paid_memberships_m"]); arm0 = float(p.loc[base_q, "arm_usd"])
    rows = []
    for i, q in enumerate(post):
        m_cf = m_prev_cf * (1 + (cf_g[q] + shift) / 100)
        arm_cf = arm0 * (1 + arm_cf_growth_q) ** (i + 1)
        m = float(p.loc[q, "paid_memberships_m"]); arm = float(p.loc[q, "arm_usd"])
        avg, avg_cf = (m + m_prev) / 2, (m_cf + m_prev_cf) / 2
        rev_cf = 3 * avg_cf * arm_cf
        rows.append({"quarter": q, "members_actual_m": m, "members_cf_m": m_cf, "arm_actual": arm,
                     "arm_cf": arm_cf, "revenue_actual_musd": float(p.loc[q, "revenue_musd"]),
                     "revenue_cf_musd": rev_cf,
                     "price_component_musd": 3 * avg * (arm - arm_cf),
                     "volume_component_musd": 3 * (avg - avg_cf) * arm_cf})
        m_prev, m_prev_cf = m, m_cf
    r = pd.DataFrame(rows)
    r["incremental_revenue_musd"] = r["revenue_actual_musd"] - r["revenue_cf_musd"]
    return r
