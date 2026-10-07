import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd, pytest
from pricing_study.data import load_panel, load_config, validate, wide, qstr, qnum
from pricing_study import synth as S, did as D, finance as F
from pricing_study.study import run_study
from pipeline.check_filings import new_earnings_filings


def test_real_data_is_clean_and_complete():
    p = load_panel()
    assert validate(p) == []
    assert p.groupby("region").size().nunique() == 1
    assert p.source_url.str.startswith("https://www.sec.gov/").all()


def test_validation_catches_a_typo():
    p = load_panel()
    p.loc[(p.region == "UCAN") & (p.quarter == "2022Q2"), "paid_memberships_m"] = 78.28
    assert any("reconcile" in x for x in validate(p))


def _fake(effect, seed=0, n=24, post=4):
    r = np.random.default_rng(seed)
    common = r.normal(0, 2, n)
    w = pd.DataFrame({"A": 8 + common + r.normal(0, .3, n), "B": 5 + .7 * common + r.normal(0, .3, n),
                      "C": 3 + .4 * common + r.normal(0, .3, n)}, index=[qstr(qnum("2017Q1") + i) for i in range(n)])
    w["T"] = -0.5 + 0.15 * w["A"] + 0.1 * w["B"] + r.normal(0, .15, n)   # outside the donors' convex hull
    w.iloc[-post:, w.columns.get_loc("T")] += effect
    return w, w.index[-post]


def test_scaled_synth_recovers_a_planted_effect():
    w, ev = _fake(-1.0)
    f = S.scaled_synth(w, "T", ["A", "B", "C"], ev, None, 4)
    assert abs(f["tau"] - (-1.0)) < 0.25 and f["p_value"] < 0.1


def test_scaled_synth_finds_nothing_when_nothing_happened():
    taus = [S.scaled_synth(*(lambda w, ev: (w, "T", ["A", "B", "C"], ev, None, 4))(*_fake(0.0, s)))["tau"] for s in range(20)]
    assert abs(np.mean(taus)) < 0.1


def test_did_equals_difference_of_means():
    w = wide(load_panel(), "member_growth_pct")
    r = D.did(w, "UCAN", ["EMEA", "LATAM", "APAC"], "2022Q1", "2018Q1", 4)
    assert r["tau"] == pytest.approx(r["post_gap_mean"] - r["pre_gap_mean"])


def test_ltv_closed_form_matches_simulation():
    c, d, arm, m = 0.02, 0.10, 15.0, 0.3
    r = (1 + d) ** (1 / 12) - 1
    sim = sum(arm * m * ((1 - c) / (1 + r)) ** t for t in range(5000))
    assert F.ltv(arm, m, c, d) == pytest.approx(sim, rel=1e-6)


def test_headline_numbers_are_internally_consistent():
    res = run_study(load_panel(), load_config())
    rv = pd.DataFrame(res["revenue"]["by_quarter"])
    assert (rv.price_component_musd + rv.volume_component_musd).sum() == pytest.approx(
        rv.incremental_revenue_musd.sum(), rel=0.03)      # decomposition closes up to rounding of reported ARM
    e = res["elasticity"]["first_4_quarters"]
    assert e["elasticity"] == pytest.approx(res["main"]["cumulative"] / res["price"]["arm"]["pct"])
    assert res["finance"]["ltv"]["breakeven_extra_churn"] > 0


def test_study_runs_on_truncated_history():
    res = run_study(load_panel("2022Q2"), load_config())
    assert res["post_quarters"] == ["2022Q1", "2022Q2"]


def test_new_filing_detection():
    sub = {"cik": "1065280", "filings": {"recent": {
        "form": ["8-K", "10-Q", "8-K", "8-K"], "filingDate": ["2026-10-15", "2026-07-20", "2026-07-16", "2026-09-01"],
        "accessionNumber": ["0001065280-26-000300", "x", "0001065280-26-000211", "y"],
        "primaryDocument": ["nflx-20261015.htm", "q.htm", "nflx-20260716.htm", "z.htm"],
        "items": ["2.02,9.01", "", "2.02,9.01", "5.02"]}}}
    found = new_earnings_filings(sub, "2026Q2")
    assert [x["filed"] for x in found] == ["2026-10-15"]
    assert found[0]["url"].endswith("/1065280/000106528026000300/nflx-20261015.htm")
    assert new_earnings_filings(sub, "2026Q3") == []
