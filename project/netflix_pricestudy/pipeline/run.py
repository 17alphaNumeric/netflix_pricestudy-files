"""Scheduled job: validate -> estimate -> monitor -> version -> log.

    python -m pipeline.run                    # live run on all data
    python -m pipeline.run --as-of 2023Q2     # replay as if run after that quarter (mode=backfill)
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pricing_study.data import load_panel, load_config, data_sha, validate
from pricing_study.study import run_study
from pricing_study.monitor import run_monitor
from pricing_study import report

REG, MON, OUT, LOG = ROOT / "registry", ROOT / "monitoring", ROOT / "outputs", ROOT / "MAINTENANCE_LOG.md"
FIELDS = ["run_id", "run_utc", "mode", "as_of_quarter", "model_version", "code_sha", "data_sha", "study_post_n",
          "study_tau", "study_se", "elasticity_4q", "incremental_revenue_musd", "monitor_z", "running_z_4q",
          "monitor_weights", "n_alerts", "alert_types"]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "nogit"


def previous_run() -> dict | None:
    f = REG / "runs.csv"
    if not f.exists():
        return None
    rows = list(csv.DictReader(open(f)))
    if not rows:
        return None
    r = rows[-1]
    return {"model_version": r["model_version"], "data_sha": r["data_sha"],
            "study_tau": float(r["study_tau"]) if r["study_tau"] else None,
            "study_post_n": int(r["study_post_n"]) if r["study_post_n"] else None,
            "monitor_weights": json.loads(r["monitor_weights"] or "{}")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of"); ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    mode = "backfill" if a.as_of else "live"
    cfg = load_config(); panel = load_panel(a.as_of)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for d in (REG / "runs", MON, OUT / "figures"):
        d.mkdir(parents=True, exist_ok=True)

    problems = validate(panel)
    if problems:                       # do not estimate on broken data; alert and stop
        mon = {"latest_quarter": panel.quarter.max(), "alerts": [{"type": "data_quality", "severity": "high", "message": p} for p in problems]}
        study = None
    else:
        study = run_study(panel, cfg)
        mon = run_monitor(panel, cfg, study, previous_run(), live=(mode == "live"))
    alerts = mon["alerts"]
    sha = data_sha(); run_id = f"{now:%Y%m%dT%H%M%SZ}-{mode}-{mon['latest_quarter']}"
    row = {"run_id": run_id, "run_utc": now.isoformat(), "mode": mode, "as_of_quarter": mon["latest_quarter"],
           "model_version": cfg["model_version"], "code_sha": git_sha(), "data_sha": sha,
           "n_alerts": len(alerts), "alert_types": ";".join(sorted({x["type"] for x in alerts}))}
    if study:
        el = study["elasticity"].get("first_4_quarters", {})
        row.update(study_post_n=len(study["post_quarters"]), study_tau=round(study["main"]["tau"], 6),
                   study_se=round(study["main"]["se"], 6), elasticity_4q=round(el.get("elasticity", float("nan")), 6),
                   incremental_revenue_musd=round(study["revenue"]["incremental_musd"], 2),
                   monitor_z=round(mon["prediction"]["z"], 4), running_z_4q=round(mon["running_z_4q"], 4),
                   monitor_weights=json.dumps({k: round(v, 4) for k, v in mon["prediction"]["weights"].items()}))
    new = not (REG / "runs.csv").exists()
    with open(REG / "runs.csv", "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    json.dump({"run": row, "config": cfg, "study": study, "monitor": mon}, open(REG / "runs" / f"{run_id}.json", "w"), indent=1, default=str)

    if mode == "live":                 # latest.* always reflects the most recent live run
        json.dump(mon, open(MON / "latest.json", "w"), indent=1, default=str)
        if study:
            json.dump(study, open(OUT / "results.json", "w"), indent=1, default=str)
            (OUT / "RESULTS.md").write_text(report.summary_md(study))
            report.make_figures(study, panel, OUT / "figures")
        body = "\n".join(f"- **{x['type']}** ({x['severity']}): {x['message']}" for x in alerts)
        (MON / "alerts.md").write_text(f"Run `{run_id}` raised {len(alerts)} alert(s).\n\n{body}\n" if alerts else "")
    hist = pd.read_csv(REG / "runs.csv")
    if hist["monitor_z"].notna().any():
        report.monitor_figure(hist.dropna(subset=["monitor_z"]), cfg["monitor"]["z_alert"], OUT / "figures" / "drift_monitor.png")

    with open(LOG, "a") as f:
        what = "; ".join(f"{x['type']}: {x['message']}" for x in alerts) or "no alerts"
        f.write(f"| {now:%Y-%m-%d %H:%M} | {mode} | {mon['latest_quarter']} | {cfg['model_version']} | {sha} | {what}{' | ' + a.note if a.note else ' | '} |\n")
    print(f"{run_id}: {len(alerts)} alert(s)")
    for x in alerts:
        print("  ALERT", x["type"], "-", x["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
