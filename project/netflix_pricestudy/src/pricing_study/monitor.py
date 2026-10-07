"""Drift monitoring for the scheduled job.

Paid memberships stopped being reported after 2024Q4, so the live monitor
tracks what Netflix still publishes: revenue by region. For each new quarter:

* input drift   - is any region's revenue growth unusual versus its trailing window?
* model drift   - does UCAN's revenue growth still track the donor-based
                  prediction (one-step-ahead standardised error, and a 4-quarter
                  running sum), and have the donor weights moved since the last run?
* result drift  - has the headline study estimate changed since the last run?
                  It should not unless source data were revised or the code changed.
* staleness     - is a new quarter overdue?
* data quality  - schema and accounting identities (see data.validate).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .data import wide, qnum, qstr, quarter_end, validate
from .synth import scaled_synth


def one_step(w, treated, donors, target_q: str, train_n: int) -> dict:
    ww = w.loc[[q for q in w.index if qnum(target_q) - train_n <= qnum(q) <= qnum(target_q)]]
    f = scaled_synth(ww, treated, donors, target_q, None, 1)
    err = f["post_gap"][0]
    return {"quarter": target_q, "actual": f["actual"][-1], "predicted": f["counterfactual"][-1],
            "error": err, "rmse_loo": f["rmse_loo"], "z": err / f["rmse_loo"], "weights": f["weights"]}


def run_monitor(panel, cfg, study: dict, previous: dict | None, today=None, live=True) -> dict:
    m, s = cfg["monitor"], cfg["study"]
    alerts = []
    for p in validate(panel):
        alerts.append({"type": "data_quality", "severity": "high", "message": p})
    w = wide(panel, "rev_growth_pct").dropna()
    latest = w.index[-1]
    out = {"latest_quarter": latest}

    # input drift
    hist = w.iloc[-(m["train_quarters"] + 1):-1]
    z_in = ((w.iloc[-1] - hist.mean()) / hist.std(ddof=1)).to_dict()
    out["input_z"] = {k: float(v) for k, v in z_in.items()}
    for r, z in z_in.items():
        if abs(z) > m["input_z_alert"]:
            alerts.append({"type": "input_drift", "severity": "medium",
                           "message": f"{r} revenue growth in {latest} is {z:+.1f} sd from its trailing {m['train_quarters']}-quarter mean"})

    # model drift: one-step-ahead errors for the last 4 quarters
    steps = [one_step(w, s["treated"], s["donors"], qstr(qnum(latest) - k), m["train_quarters"]) for k in (3, 2, 1, 0)]
    cur = steps[-1]; run4 = float(sum(x["z"] for x in steps) / 2)      # sum of 4 z's / sqrt(4)
    out.update(prediction=cur, running_z_4q=run4, last4_z=[x["z"] for x in steps])
    if abs(cur["z"]) > m["z_alert"]:
        alerts.append({"type": "model_drift", "severity": "high",
                       "message": f"UCAN revenue growth in {latest} was {cur['actual']:.2f}% vs {cur['predicted']:.2f}% predicted (z={cur['z']:+.1f})"})
    if abs(run4) > m["z_alert"]:
        alerts.append({"type": "model_drift", "severity": "high",
                       "message": f"UCAN has run persistently {'above' if run4 > 0 else 'below'} its donor-based prediction for 4 quarters (z={run4:+.1f})"})
    if previous:
        pw = previous.get("monitor_weights") or {}
        l1 = sum(abs(cur["weights"].get(k, 0) - pw.get(k, 0)) for k in set(cur["weights"]) | set(pw))
        out["weight_l1_change"] = float(l1)
        if pw and l1 > m["weight_l1_alert"]:
            alerts.append({"type": "model_drift", "severity": "medium",
                           "message": f"monitor donor weights moved by {l1:.2f} (L1) since the last run"})
        if previous.get("model_version") == cfg["model_version"] and previous.get("study_tau") is not None \
                and previous.get("study_post_n") == len(study["post_quarters"]):
            ch = abs(study["main"]["tau"] - previous["study_tau"])
            out["study_tau_change"] = float(ch)
            if ch > m["estimate_change_alert_pp"]:
                alerts.append({"type": "result_drift", "severity": "high",
                               "message": f"headline effect moved by {ch:.2f} pp with no version change; source data were probably revised"})
    if live:
        age = (pd.Timestamp(today or pd.Timestamp.now(tz='UTC').date()) - quarter_end(latest)).days
        out["days_since_quarter_end"] = int(age)
        if age > m["stale_days"]:
            alerts.append({"type": "stale_data", "severity": "medium",
                           "message": f"latest quarter is {latest} ({age} days old); add the new quarter to data/raw"})
    out["alerts"] = alerts
    return out
