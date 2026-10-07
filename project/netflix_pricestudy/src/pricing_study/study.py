"""Runs the whole study and returns one JSON-serialisable dict."""
from __future__ import annotations
import numpy as np
from . import did as D, synth as S, economics as E, finance as F
from .data import wide, qnum, qstr


def run_study(panel, cfg) -> dict:
    s = cfg["study"]; tr, dn, ev = s["treated"], s["donors"], s["event_quarter"]
    last_m = panel.dropna(subset=["paid_memberships_m"])["t"].max()
    post_n = int(min(s["post_quarters"], last_m - qnum(ev) + 1))
    w = wide(panel, "member_growth_pct")

    main = S.scaled_synth(w, tr, dn, ev, None, post_n)
    res = {"event_quarter": ev, "post_quarters": main["post_quarters"], "outcome": "QoQ growth in paid memberships (%)",
           "main": {k: main[k] for k in ("intercept", "weights", "rmse_pre", "rmse_loo", "n_pre", "tau", "se", "ci_low",
                                         "ci_high", "p_value", "cumulative", "cumulative_se", "post_gap", "rmspe_ratio")},
           "series": {k: main[k] for k in ("quarters", "actual", "counterfactual", "gap", "pre_mask")}}
    res["windows"] = {f"first_{k}_quarters": S.window_effect(main, k) for k in (2, 4) if k <= post_n}

    # --- robustness -----------------------------------------------------
    rb = {}
    rb["did_equal_weights_no_trend"] = D.did(w, tr, dn, ev, s["pre_start"], post_n)
    rb["did_equal_weights_linear_trend"] = D.did(w, tr, dn, ev, s["pre_start"], post_n, trend=True)
    rb["did_trend_and_seasonality"] = D.did(w, tr, dn, ev, s["pre_start"], post_n, trend=True, seasonal=True)
    rb["did_placebo_in_time"] = D.placebo_in_time(w, tr, dn, ev, s["pre_start"], post_n, trend=True)
    rb["demeaned_synth"] = S.demeaned_synth(w, tr, dn, ev, s["pre_start"], post_n)
    spec = {}
    spec["pre from 2018Q1"] = S.scaled_synth(w, tr, dn, ev, "2018Q1", post_n)
    spec["pre from 2019Q1"] = S.scaled_synth(w, tr, dn, ev, "2019Q1", post_n)
    spec["drop COVID quarters 2020Q1-Q2"] = S.scaled_synth(w, tr, dn, ev, None, post_n, drop=("2020Q1", "2020Q2"))
    spec["drop earlier UCAN price quarters"] = S.scaled_synth(w, tr, dn, ev, None, post_n,
                                                              drop=("2019Q1", "2019Q2", "2020Q4", "2021Q1"))
    rx = s["russia_exit"]                       # add back members lost to the Russia exit
    p2 = panel.copy()
    m = (p2.region == rx["region"]) & (p2.quarter == rx["quarter"])
    prev = p2.loc[(p2.region == rx["region"]) & (p2.t == qnum(rx["quarter"]) - 1), "paid_memberships_m"].iloc[0]
    p2.loc[m, "member_growth_pct"] = 100 * (p2.loc[m, "paid_net_adds_m"] + rx["members_m"]) / prev
    spec["EMEA adjusted for Russia exit"] = S.scaled_synth(wide(p2, "member_growth_pct"), tr, dn, ev, None, post_n)
    for d in dn:
        spec[f"without {d}"] = S.scaled_synth(w, tr, [x for x in dn if x != d], ev, None, post_n)
    rb["spec_curve"] = {k: {"tau": v["tau"], "se": v["se"], "cumulative": v["cumulative"],
                            "first_2q": float(np.sum(v["post_gap"][:2])), "rmse_loo": v["rmse_loo"]} for k, v in spec.items()}
    rb["placebo_in_space"] = S.placebo_in_space(w, tr, dn, ev, None, post_n)
    rb["placebo_in_time"] = S.placebo_in_time(w, tr, dn, ev, None, post_n)
    res["robustness"] = rb
    res["event_study_did"] = D.event_study(w, tr, dn, ev, s["pre_start"], post_n).to_dict("records")

    # --- economics --------------------------------------------------------
    arm = E.arm_change(panel, tr, s["arm_baseline_quarter"], s["arm_post_quarters"])
    res["price"] = {"list": E.list_price_change(), "arm": arm}
    res["elasticity"] = E.elasticity(main, arm["pct"])
    base = s["arm_baseline_quarter"]
    rev = E.revenue_counterfactual(panel, main, tr, base)
    lo = E.revenue_counterfactual(panel, main, tr, base, shift=+1.96 * main["se"])   # stronger counterfactual
    hi = E.revenue_counterfactual(panel, main, tr, base, shift=-1.96 * main["se"])
    drift = E.revenue_counterfactual(panel, main, tr, base, arm_cf_growth_q=0.005)
    tot = rev["revenue_cf_musd"].sum()
    res["revenue"] = {"by_quarter": rev.round(3).to_dict("records"),
                      "incremental_musd": float(rev.incremental_revenue_musd.sum()),
                      "incremental_pct": 100 * float(rev.incremental_revenue_musd.sum() / tot),
                      "ci_low_musd": float(lo.incremental_revenue_musd.sum()),
                      "ci_high_musd": float(hi.incremental_revenue_musd.sum()),
                      "if_arm_would_have_drifted_2pct_a_year_musd": float(drift.incremental_revenue_musd.sum()),
                      "price_component_musd": float(rev.price_component_musd.sum()),
                      "volume_component_musd": float(rev.volume_component_musd.sum())}

    # --- finance -----------------------------------------------------------
    f = cfg["finance"]; cms = F.contribution_margins()
    yr = int(ev[:4]); cm = float(cms.set_index("year").loc[yr, "contribution_margin"])
    w4 = res["windows"].get("first_4_quarters") or res["windows"][f"first_{min(2, post_n)}_quarters"]
    res["finance"] = {"flow_through": f["price_flow_through"], "churn_baseline": f["monthly_churn_baseline"], "margins": cms.round(4).to_dict("records"), "contribution_margin_used": cm,
                      "ltv": F.ltv_scenarios(arm["arm_before"], arm["arm_after"], cm, cfg, w4["cumulative"], w4["ci_low"]),
                      "cac_payback": F.cac_payback(panel, yr, cm, f["monthly_churn_baseline"]),
                      "price_change_payback": F.price_change_payback(rev, f["price_flow_through"]),
                      "price_change_payback_pessimistic": F.price_change_payback(lo, f["price_flow_through"])}
    return res
