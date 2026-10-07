"""Ask SEC EDGAR whether Netflix has published a quarter we have not ingested.

Writes monitoring/new_filing.md when an earnings 8-K (Item 2.02) is newer than
the data. Ingestion is deliberately manual: copy the four regional revenue
figures from the letter into scripts/build_raw_data.py, re-run it, and commit.
The validation step and the result-drift alert then guard against typos.

NOTE: not exercised against the live EDGAR API in the build environment
(sec.gov was unreachable there). The parsing logic is unit-tested on a fixture.
"""
from __future__ import annotations
import json, os, pathlib, sys, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from pricing_study.data import load_panel, load_config, quarter_end


def new_earnings_filings(submissions: dict, latest_quarter: str, grace_days: int = 45) -> list[dict]:
    """Earnings 8-Ks filed more than `grace_days` after the latest quarter we hold.
    A quarter's own results arrive ~3 weeks after it ends; the next quarter's ~16 weeks after."""
    r = submissions["filings"]["recent"]
    cutoff = quarter_end(latest_quarter) + pd.Timedelta(days=grace_days)
    out = []
    for form, date, acc, doc, items in zip(r["form"], r["filingDate"], r["accessionNumber"], r["primaryDocument"], r.get("items", [""] * len(r["form"]))):
        if form == "8-K" and "2.02" in (items or "") and pd.Timestamp(date) > cutoff:
            out.append({"filed": date, "url": f"https://www.sec.gov/Archives/edgar/data/{int(submissions['cik'])}/{acc.replace('-', '')}/{doc}"})
    return out


def main() -> int:
    cfg = load_config(); latest = load_panel().quarter.max()
    ua = cfg["edgar"]["user_agent"].replace("set CONTACT_EMAIL secret", os.environ.get("CONTACT_EMAIL", "no-contact-set"))
    out = ROOT / "monitoring" / "new_filing.md"; out.parent.mkdir(exist_ok=True)
    try:
        req = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cfg['edgar']['cik']}.json", headers={"User-Agent": ua})
        sub = json.load(urllib.request.urlopen(req, timeout=30))
        found = new_earnings_filings(sub, latest)
    except Exception as e:                      # a failed check must not break the scheduled run
        print("EDGAR check failed:", e); out.write_text(""); return 0
    out.write_text("".join(f"New Netflix earnings release filed {x['filed']}: {x['url']}\n\nLatest quarter in data: {latest}. Add the new quarter (see README, 'Adding a quarter').\n" for x in found[:1]))
    print(f"latest quarter in data {latest}; {len(found)} newer earnings filing(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
