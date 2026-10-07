"""Lifetime value, contribution margin and payback.

Netflix does not disclose churn, gross additions or regional costs. Everything
that depends on them is driven by the assumptions in config.yaml and is
reported with a sensitivity table. Margins come from the audited income
statement and are company-wide, not UCAN-specific.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .data import ROOT


def contribution_margins() -> pd.DataFrame:
    """Contribution margin as Netflix defined it when it reported segment
    contribution profit: (revenue - cost of revenues - marketing) / revenue."""
    f = pd.read_csv(ROOT / "data/raw/netflix_income_statement.csv")
    f["gross_margin"] = 1 - f.cost_of_revenues_kusd / f.revenues_kusd
    f["contribution_margin"] = 1 - (f.cost_of_revenues_kusd + f.sales_and_marketing_kusd) / f.revenues_kusd
    f["operating_margin"] = f.operating_income_kusd / f.revenues_kusd
    return f[["year", "gross_margin", "contribution_margin", "operating_margin"]]


def ltv(arm: float, margin: float, monthly_churn: float, annual_discount: float) -> float:
    """Discounted contribution over a member's expected life (billed monthly in advance)."""
    r = (1 + annual_discount) ** (1 / 12) - 1
    return arm * margin / (1 - (1 - monthly_churn) / (1 + r))


def ltv_scenarios(arm_before, arm_after, cm, cfg, quantity_effect_pct, quantity_ci_low_pct) -> dict:
    """LTV before and after the price change.

    After: each member pays more, the extra revenue converts at
    `price_flow_through`, and monthly churn rises by the membership shortfall
    spread over 12 months (treated as permanent, which is conservative)."""
    f = cfg["finance"]; disc = f["annual_discount_rate"]; share = f["share_of_effect_from_churn"]
    margin_after = (arm_before * cm + (arm_after - arm_before) * f["price_flow_through"]) / arm_after
    extra = lambda eff: max(0.0, -eff) / 100 / 12 * share
    rows = []
    for c in f["churn_sensitivity"]:
        before = ltv(arm_before, cm, c, disc)
        rows.append({"baseline_monthly_churn": c, "ltv_before": before,
                     "ltv_after_point": ltv(arm_after, margin_after, c + extra(quantity_effect_pct), disc),
                     "ltv_after_pessimistic": ltv(arm_after, margin_after, c + extra(quantity_ci_low_pct), disc)})
    c0 = f["monthly_churn_baseline"]; base = ltv(arm_before, cm, c0, disc)
    # churn at which LTV after = LTV before
    r = (1 + disc) ** (1 / 12) - 1
    be_churn = 1 - (1 + r) * (1 - arm_after * margin_after / base)
    return {"margin_before": cm, "margin_after": margin_after,
            "extra_monthly_churn_point": extra(quantity_effect_pct),
            "extra_monthly_churn_pessimistic": extra(quantity_ci_low_pct),
            "table": rows, "breakeven_monthly_churn": be_churn,
            "breakeven_extra_churn": be_churn - c0}


def cac_payback(panel: pd.DataFrame, year: int, cm: float, monthly_churn: float) -> dict:
    """Company-wide months to recover marketing spend per gross addition.
    Gross adds are NOT disclosed: gross = net adds + assumed churn x average base."""
    inc = pd.read_csv(ROOT / "data/raw/netflix_income_statement.csv").set_index("year")
    p = panel[panel.quarter.str[:4] == str(year)]
    tot = p.groupby("quarter")[["paid_memberships_m", "paid_net_adds_m", "revenue_musd"]].sum()
    start = panel[panel.quarter == f"{year-1}Q4"]["paid_memberships_m"].sum()
    avg_base = (start + tot["paid_memberships_m"].iloc[-1]) / 2
    gross = tot["paid_net_adds_m"].sum() + monthly_churn * 12 * avg_base
    cac = inc.loc[year, "sales_and_marketing_kusd"] / 1000 / gross
    arm = tot["revenue_musd"].sum() / (12 * avg_base)
    return {"year": year, "gross_adds_m_assumed": float(gross), "cac_usd": float(cac),
            "arm_usd": float(arm), "payback_months": float(cac / (arm * cm))}


def price_change_payback(rev: pd.DataFrame, flow_through: float) -> dict:
    """Quarter in which cumulative incremental contribution turns positive."""
    c = (rev["incremental_revenue_musd"] * flow_through).cumsum()
    pos = rev["quarter"][c > 0]
    return {"cumulative_contribution_musd": dict(zip(rev["quarter"], c.round(1))),
            "payback_quarter": pos.iloc[0] if len(pos) and (c[c.index >= pos.index[0]] > 0).all() else None,
            "incremental_contribution_musd": float(c.iloc[-1])}
