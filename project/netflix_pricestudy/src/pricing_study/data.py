"""Load and validate the Netflix regional panel."""
from __future__ import annotations
import hashlib, pathlib
import numpy as np, pandas as pd, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/netflix_regional_quarterly.csv"
REGIONS = ["UCAN", "EMEA", "LATAM", "APAC"]


def load_config(path=None) -> dict:
    return yaml.safe_load(open(path or ROOT / "config.yaml"))


def qnum(q: str) -> int:
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qstr(n: int) -> str:
    return f"{n // 4}Q{n % 4 + 1}"


def quarter_end(q: str) -> pd.Timestamp:
    return pd.Period(q, freq="Q").end_time.normalize()


def data_sha(path=RAW) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:12]


def load_panel(as_of: str | None = None, path=RAW) -> pd.DataFrame:
    """Tidy panel. `as_of` truncates to quarters <= as_of (used by the backfill replay)."""
    d = pd.read_csv(path)
    d["t"] = d["quarter"].map(qnum)
    if as_of:
        d = d[d["t"] <= qnum(as_of)]
    d = d.sort_values(["region", "t"]).reset_index(drop=True)
    g = d.groupby("region")
    prev = g["paid_memberships_m"].shift()
    d["member_growth_pct"] = 100 * d["paid_net_adds_m"] / prev        # QoQ growth of paid memberships
    d["rev_growth_pct"] = 100 * np.log(d["revenue_musd"] / g["revenue_musd"].shift())
    d["log_members"] = np.log(d["paid_memberships_m"])
    return d


def wide(d: pd.DataFrame, col: str) -> pd.DataFrame:
    w = d.pivot(index="t", columns="region", values=col)
    w.index = [qstr(i) for i in w.index]
    return w


def validate(d: pd.DataFrame) -> list[str]:
    """Return a list of problems (empty list = clean)."""
    p = []
    if set(d["region"]) != set(REGIONS):
        p.append(f"unexpected regions: {sorted(set(d['region']))}")
    if d.duplicated(["region", "quarter"]).any():
        p.append("duplicate region-quarter rows")
    for r, x in d.groupby("region"):
        if (np.diff(x["t"]) != 1).any():
            p.append(f"{r}: gap in quarters")
        if (x["revenue_musd"] <= 0).any() or x["revenue_musd"].isna().any():
            p.append(f"{r}: missing or non-positive revenue")
        m = x.dropna(subset=["paid_memberships_m"])
        # identity 1: memberships(t) = memberships(t-1) + net adds(t), within rounding
        gap = (m["paid_memberships_m"].diff() - m["paid_net_adds_m"]).abs().iloc[1:]
        if (gap > 0.025).any():
            p.append(f"{r}: net adds do not reconcile to memberships")
        # identity 2: revenue = ARM x average memberships x 3 months, within 1%
        avg = (m["paid_memberships_m"] + m["paid_memberships_m"].shift()) / 2
        err = (m["revenue_musd"] / (3 * avg * m["arm_usd"]) - 1).abs().iloc[1:]
        if (err > 0.01).any():
            p.append(f"{r}: revenue does not reconcile to ARM x memberships")
    if d.groupby("region")["t"].max().nunique() != 1:
        p.append("regions end in different quarters")
    return p
