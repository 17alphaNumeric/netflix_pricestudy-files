"""Figures and a short markdown summary written on every run."""
from __future__ import annotations
import pathlib
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

INK, MUTED, A, B, GRID = "#1f2933", "#7b8794", "#c2410c", "#0f766e", "#e4e7eb"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True, "figure.dpi": 130})


def _ticks(ax, qs, every=2):
    ax.set_xticks(range(0, len(qs), every)); ax.set_xticklabels([qs[i] for i in range(0, len(qs), every)], rotation=45, ha="right")


def make_figures(res: dict, panel: pd.DataFrame, outdir: pathlib.Path):
    outdir.mkdir(parents=True, exist_ok=True)
    s = res["series"]; qs = s["quarters"]; e = qs.index(res["event_quarter"])

    fig, ax = plt.subplots(2, 1, figsize=(8, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    ax[0].plot(s["actual"], color=A, lw=2, label="UCAN actual")
    ax[0].plot(s["counterfactual"], color=B, lw=2, ls="--", label="Synthetic UCAN (no price change)")
    ax[0].axvline(e - 0.5, color=INK, lw=1); ax[0].text(e - 0.4, max(s["actual"]) * 0.95, "Jan 2022\nprice increase", fontsize=9)
    ax[0].set_ylabel("Paid membership growth, % QoQ"); ax[0].legend(frameon=False, loc="lower left")
    ax[0].set_title("UCAN membership growth vs synthetic control", loc="left", fontweight="bold")
    gap = np.array(s["gap"]); band = 1.96 * res["main"]["rmse_loo"]
    ax[1].bar(range(len(qs)), gap, color=[MUTED if i < e else A for i in range(len(qs))], width=0.7)
    ax[1].axhspan(-band, band, color=B, alpha=0.08); ax[1].axhline(0, color=INK, lw=0.8); ax[1].axvline(e - 0.5, color=INK, lw=1)
    ax[1].set_ylabel("Gap, pp"); ax[1].text(0, band * 0.8, "shaded: ±1.96 × leave-one-out pre-period RMSE", fontsize=8, color=MUTED)
    _ticks(ax[1], qs); fig.tight_layout(); fig.savefig(outdir / "synthetic_control.png"); plt.close(fig)

    es = pd.DataFrame(res["event_study_did"])
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(es["rel"], es["gap"], marker="o", color=A, lw=1.5)
    ax.axvline(-0.5, color=INK, lw=1); ax.set_xlabel("Quarters relative to price change")
    ax.set_ylabel("UCAN minus donor average, pp")
    ax.set_title("Why plain DiD fails: the pre-period gap is trending, not parallel", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(outdir / "did_pretrend.png"); plt.close(fig)

    sc = res["robustness"]["spec_curve"]; names = ["Main specification"] + list(sc)
    taus = [res["main"]["tau"]] + [v["tau"] for v in sc.values()]; ses = [res["main"]["se"]] + [v["se"] for v in sc.values()]
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(names))[::-1]
    ax.errorbar(taus, y, xerr=1.96 * np.array(ses), fmt="o", color=A, ecolor=MUTED, capsize=3)
    ax.axvline(0, color=INK, lw=0.8); ax.set_yticks(y); ax.set_yticklabels(names)
    ax.set_xlabel("Effect on membership growth, pp per quarter (95% interval)")
    ax.set_title("Robustness: the estimate across specifications", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(outdir / "spec_curve.png"); plt.close(fig)

    rv = pd.DataFrame(res["revenue"]["by_quarter"])
    fig, ax = plt.subplots(figsize=(8, 3.6)); x = np.arange(len(rv))
    ax.bar(x - 0.2, rv["revenue_cf_musd"], 0.4, color=B, label="Counterfactual (no price change)")
    ax.bar(x + 0.2, rv["revenue_actual_musd"], 0.4, color=A, label="Actual")
    for i, v in enumerate(rv["incremental_revenue_musd"]):
        ax.text(i + 0.2, rv["revenue_actual_musd"][i] + 30, f"+${v:,.0f}M", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(rv["quarter"]); ax.set_ylim(2800, None); ax.set_ylabel("UCAN revenue, $M")
    ax.legend(frameon=False, loc="upper left"); ax.set_title("UCAN revenue: actual vs counterfactual", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(outdir / "revenue.png"); plt.close(fig)


def monitor_figure(history: pd.DataFrame, z_alert: float, out: pathlib.Path):
    h = history.drop_duplicates("as_of_quarter", keep="last")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.axhspan(-z_alert, z_alert, color=B, alpha=0.08)
    ax.plot(h["as_of_quarter"], h["monitor_z"], marker="o", color=A, label="One-step-ahead error (z)")
    ax.plot(h["as_of_quarter"], h["running_z_4q"], color=INK, ls="--", lw=1, label="4-quarter running z")
    ax.axhline(0, color=INK, lw=0.8); ax.legend(frameon=False, fontsize=8)
    ax.set_title("Drift monitor: UCAN revenue growth vs donor-based prediction", loc="left", fontweight="bold")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right"); fig.tight_layout(); fig.savefig(out); plt.close(fig)


def summary_md(res: dict) -> str:
    m, el, rv, fn = res["main"], res["elasticity"], res["revenue"], res["finance"]
    L = ["# Results summary (generated by pipeline/run.py - do not edit)", "",
         f"- Event: UCAN price increase, {res['event_quarter']}. Post window: {res['post_quarters'][0]} to {res['post_quarters'][-1]}.",
         f"- Realised price (ARM) change: {res['price']['arm']['pct']:+.1f}% (list prices {res['price']['list']['simple_mean_pct']:+.1f}%).",
         f"- Effect on membership growth: {m['tau']:+.2f} pp per quarter (95% CI {m['ci_low']:+.2f} to {m['ci_high']:+.2f}, permutation p = {m['p_value']:.2f}).",
         f"- Donor weights: " + ", ".join(f"{k} {v:.2f}" for k, v in m["weights"].items()) + f"; leave-one-out pre-period RMSE {m['rmse_loo']:.2f} pp."]
    for k, v in el.items():
        L.append(f"- Elasticity, {k.replace('_', ' ')}: {v['elasticity']:+.2f} (95% CI {v['ci_low']:+.2f} to {v['ci_high']:+.2f}); membership base {v['quantity_effect_pct']:+.1f}% vs counterfactual.")
    L += [f"- Incremental UCAN revenue over the post window: ${rv['incremental_musd']:,.0f}M ({rv['incremental_pct']:+.1f}%), range ${rv['ci_low_musd']:,.0f}M to ${rv['ci_high_musd']:,.0f}M.",
          f"- Contribution margin used ({res['event_quarter'][:4]}, company-wide): {100*fn['contribution_margin_used']:.1f}%.",
          f"- Incremental contribution at {100*fn['flow_through']:.0f}% flow-through: ${fn['price_change_payback']['incremental_contribution_musd']:,.0f}M; payback quarter: {fn['price_change_payback']['payback_quarter']}.",
          "", "| Baseline monthly churn (assumed) | LTV before | LTV after (point) | LTV after (pessimistic) |", "|---|---|---|---|"]
    for r in fn["ltv"]["table"]:
        L.append(f"| {100*r['baseline_monthly_churn']:.1f}% | ${r['ltv_before']:,.0f} | ${r['ltv_after_point']:,.0f} | ${r['ltv_after_pessimistic']:,.0f} |")
    L += ["", f"- Break-even: LTV is unchanged only if monthly churn rises by {100*fn['ltv']['breakeven_extra_churn']:.2f} pp (from {100*fn['churn_baseline']:.1f}% baseline).",
          f"- Company-wide CAC payback ({fn['cac_payback']['year']}, gross adds assumed): ${fn['cac_payback']['cac_usd']:.0f} per gross add, {fn['cac_payback']['payback_months']:.1f} months."]
    return "\n".join(L) + "\n"
