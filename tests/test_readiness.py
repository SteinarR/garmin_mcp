"""
Tests for get_readiness_breakdown and its HRV scoring helpers.

These run without Garmin credentials or network access: the client is a stub
returning canned payloads in the shapes live Garmin and the ingested-data cache
actually produce.
"""

import asyncio
import json

import pytest

from garmin_mcp import recommendations
from garmin_mcp.recommendations import (
    _extract_hrv_baseline,
    _extract_hrv_value,
    _first_number,
    _garmin_hrv_factor,
    _garmin_readiness_score,
    _score_hrv_against_baseline,
)

DATE = "2026-08-01"

# The baseline from the case recorded in TOOLS.md: a 36 ms night that Garmin
# itself rates BALANCED / 96 GOOD, but the old fixed 20-100 ms scale scored 20.
BASELINE = {"lowUpper": 32, "balancedLow": 36, "balancedUpper": 55, "markerValue": 0.45}


def live_hrv(value=36, baseline=BASELINE):
    """The shape live Garmin returns: nested under hrvSummary."""
    summary = {"calendarDate": DATE, "lastNightAvg": value, "weeklyAvg": 42, "status": "BALANCED"}
    if baseline is not None:
        summary["baseline"] = baseline
    return {"hrvSummary": summary, "hrvReadings": []}


def cached_hrv(value=36):
    """The shape cache.py produces: flattened, no baseline, tagged partial."""
    return {
        "avgHrv": value,
        "average": value,
        "hrvStatus": "BALANCED",
        "calendarDate": DATE,
        "_partial": True,
    }


class StubClient:
    """Returns canned payloads; any component can be knocked out with None."""

    def __init__(self, sleep=True, body_battery=True, hrv=None, stress=True, readiness=None):
        self._sleep = sleep
        self._body_battery = body_battery
        self._hrv = hrv
        self._stress = stress
        self._readiness = readiness

    # Extra reads used by the range tools, not by get_readiness_breakdown.
    def get_rhr_day(self, cdate, *a, **k):
        return {"restingHeartRate": 52}

    def get_stats(self, cdate, *a, **k):
        return {"steps": 9000}

    def get_heart_rates(self, cdate, *a, **k):
        return {"restingHeartRate": 52}

    def get_sleep_data(self, cdate, *a, **k):
        if not self._sleep:
            return None
        return {"dailySleepDTO": {"sleepTimeSeconds": 8 * 3600}}

    def get_body_battery(self, start, end, *a, **k):
        if not self._body_battery:
            return None
        return [{"bodyBatteryValue": 70}, {"bodyBatteryValue": 80}]

    def get_hrv_data(self, cdate, *a, **k):
        return self._hrv

    def get_stress_data(self, cdate, *a, **k):
        if not self._stress:
            return None
        return {"avgStressLevel": 25}

    def get_training_readiness(self, cdate, *a, **k):
        return self._readiness


class FakeApp:
    """Collects the functions register_tools decorates."""

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def tools():
    """Registers the tool set once and yields a runner for any tool by name."""
    app = FakeApp()
    recommendations.register_tools(app)

    def run(name, client, *args):
        recommendations.configure(client)
        return json.loads(asyncio.run(app.tools[name](*args)))

    yield run
    recommendations.configure(None)


@pytest.fixture
def breakdown(tools):
    """Returns a caller that configures the stub client and runs the tool."""

    def run(client, date=DATE):
        return tools("get_readiness_breakdown", client, date)

    return run


# --- HRV value extraction -------------------------------------------------


def test_hrv_read_from_live_nested_shape():
    """The regression: reading only the flat keys returned None on live data."""
    assert _extract_hrv_value(live_hrv(36)) == 36.0


def test_hrv_read_from_cached_flat_shape():
    assert _extract_hrv_value(cached_hrv(36)) == 36.0


def test_hrv_live_shape_preferred_over_stale_flat_key():
    payload = live_hrv(36)
    payload["avgHrv"] = 99
    assert _extract_hrv_value(payload) == 36.0


def test_hrv_missing_returns_none():
    assert _extract_hrv_value({"hrvSummary": {}}) is None
    assert _extract_hrv_value(None) is None
    assert _extract_hrv_value("not a dict") is None


def test_first_number_keeps_a_real_zero():
    """`a or b` would skip 0 here and fall through to the next candidate."""
    assert _first_number(0, 42) == 0.0
    assert _first_number(None, 42) == 42.0
    assert _first_number(True, 7) == 7.0
    assert _first_number(None, None) is None


# --- Baseline scoring -----------------------------------------------------


def test_baseline_extracted_from_live_payload():
    baseline = _extract_hrv_baseline(live_hrv())
    assert baseline == {"low_upper": 32.0, "balanced_low": 36.0, "balanced_upper": 55.0}


def test_baseline_absent_from_cached_payload():
    assert _extract_hrv_baseline(cached_hrv()) is None


def test_baseline_rejected_when_band_is_degenerate():
    assert _extract_hrv_baseline(live_hrv(baseline={"balancedLow": 50, "balancedUpper": 50})) is None


def test_balanced_night_no_longer_scores_as_failure():
    """The documented defect: 36 ms scored 20/100 on the old fixed scale."""
    baseline = _extract_hrv_baseline(live_hrv())
    assert _score_hrv_against_baseline(36.0, baseline) == 60.0


def test_baseline_scoring_spans_the_balanced_band():
    baseline = _extract_hrv_baseline(live_hrv())
    assert _score_hrv_against_baseline(55.0, baseline) == 90.0
    mid = _score_hrv_against_baseline(45.5, baseline)
    assert 70.0 < mid < 80.0


def test_baseline_scoring_is_monotonic():
    baseline = _extract_hrv_baseline(live_hrv())
    scores = [_score_hrv_against_baseline(v, baseline) for v in range(10, 90, 2)]
    assert scores == sorted(scores)
    assert all(0.0 <= s <= 100.0 for s in scores)


def test_low_hrv_still_scores_low():
    baseline = _extract_hrv_baseline(live_hrv())
    assert _score_hrv_against_baseline(20.0, baseline) < 20.0
    assert _score_hrv_against_baseline(5.0, baseline) == 0.0


# --- Garmin's own numbers -------------------------------------------------


def test_garmin_factors_read_from_list_shape():
    payload = [{"score": 72, "hrvFactorPercent": 96, "sleepScore": 80}]
    assert _garmin_readiness_score(payload) == 72.0
    assert _garmin_hrv_factor(payload) == 96.0


def test_garmin_readiness_read_from_cached_dict_shape():
    payload = {"score": 64, "trainingReadiness": 64, "_partial": True}
    assert _garmin_readiness_score(payload) == 64.0
    assert _garmin_hrv_factor(payload) is None


def test_garmin_readiness_read_from_nested_shape():
    assert _garmin_readiness_score({"trainingReadiness": {"value": 55}}) == 55.0


def test_garmin_factors_tolerate_empty_payloads():
    for payload in ([], None, {}, "unexpected"):
        assert _garmin_readiness_score(payload) is None
        assert _garmin_hrv_factor(payload) is None


# --- The tool end to end --------------------------------------------------


def test_hrv_component_resolves_on_live_data(breakdown):
    """Before the fix this component was None on every live call."""
    result = breakdown(StubClient(hrv=live_hrv(36)))
    assert result["components"]["hrv_score"] is not None
    assert result["hrv_ms"] == 36.0
    assert result["components_missing"] == []
    assert set(result["components_used"]) == {
        "sleep_score",
        "body_battery_score",
        "hrv_score",
        "stress_inverse_score",
    }


def test_garmin_hrv_factor_wins_when_available(breakdown):
    result = breakdown(
        StubClient(hrv=live_hrv(36), readiness=[{"score": 72, "hrvFactorPercent": 96}])
    )
    assert result["components"]["hrv_score"] == 96.0
    assert result["hrv_scoring_method"] == "garmin_hrv_factor"
    assert result["garmin_training_readiness"] == 72.0


def test_personal_baseline_used_without_garmin_factor(breakdown):
    result = breakdown(StubClient(hrv=live_hrv(36)))
    assert result["hrv_scoring_method"] == "personal_baseline"
    assert result["components"]["hrv_score"] == 60.0


def test_cached_payload_falls_back_to_population_scale(breakdown):
    """No baseline is stored in the cache, so scoring says so rather than guessing quietly."""
    result = breakdown(StubClient(hrv=cached_hrv(36)))
    assert result["hrv_scoring_method"] == "population_scale_approximate"
    assert result["components"]["hrv_score"] is not None


def test_missing_hrv_is_named_not_hidden(breakdown):
    """The composite silently became a 3-way average; now it reports which 3."""
    result = breakdown(StubClient(hrv=None))
    assert result["components"]["hrv_score"] is None
    assert result["components_missing"] == ["hrv_score"]
    assert "hrv_score" not in result["components_used"]
    assert len(result["components_used"]) == 3


def test_composite_averages_only_resolved_components(breakdown):
    result = breakdown(StubClient(hrv=None, stress=False))
    used = result["components_used"]
    expected = sum(result["components"][name] for name in used) / len(used)
    assert result["readiness_score"] == pytest.approx(round(expected, 2))


def test_no_components_yields_null_readiness(breakdown):
    result = breakdown(StubClient(sleep=False, body_battery=False, hrv=None, stress=False))
    assert result["readiness_score"] is None
    assert result["components_used"] == []
    assert len(result["components_missing"]) == 4


def test_failing_readiness_call_does_not_break_the_tool(breakdown):
    class Exploding(StubClient):
        def get_training_readiness(self, cdate, *a, **k):
            raise RuntimeError("garmin said no")

    result = breakdown(Exploding(hrv=live_hrv(36)))
    assert result["garmin_training_readiness"] is None
    assert result["components"]["hrv_score"] == 60.0


def test_invalid_date_is_rejected(breakdown):
    recommendations.configure(StubClient())
    app = FakeApp()
    recommendations.register_tools(app)
    out = asyncio.run(app.tools["get_readiness_breakdown"]("not-a-date"))
    assert "Invalid date" in out


# --- The other four call sites of the same defect -------------------------
#
# get_trends, detect_anomalies, get_period_summary and get_data_completeness
# each read HRV with the same flat-key pattern. Every one of them returned
# None/False for HRV on live payloads before the shared helper landed.

RANGE_START = "2026-08-01"
RANGE_END = "2026-08-02"


def test_trends_reads_live_hrv(tools):
    result = tools("get_trends", StubClient(hrv=live_hrv(36)), RANGE_START, RANGE_END, ["hrv"])
    assert result["series"]
    assert all(day["hrv"] == 36.0 for day in result["series"])


def test_trends_still_reads_the_cached_shape(tools):
    """The cached flat shape worked throughout; guard against regressing it."""
    result = tools("get_trends", StubClient(hrv=cached_hrv(36)), RANGE_START, RANGE_END, ["hrv"])
    assert all(day["hrv"] == 36.0 for day in result["series"])


def test_detect_anomalies_flags_an_hrv_drop_on_live_data(tools):
    """With HRV stuck at None, no drop could ever be detected — the flag is the proof."""

    class PerDayHrv(StubClient):
        def get_hrv_data(self, cdate, *a, **k):
            return live_hrv(30 if cdate == "2026-08-05" else 60)

    result = tools("detect_anomalies", PerDayHrv(), "2026-08-01", "2026-08-05")
    flagged = {day["date"]: day["flags"] for day in result["anomalies"]}
    assert "hrv_depressed" in flagged.get("2026-08-05", [])


def test_detect_anomalies_finds_no_drop_when_hrv_is_steady(tools):
    result = tools("detect_anomalies", StubClient(hrv=live_hrv(60)), "2026-08-01", "2026-08-05")
    for day in result["anomalies"]:
        assert "hrv_depressed" not in day["flags"]


def test_data_completeness_counts_live_hrv_as_present(tools):
    result = tools("get_data_completeness", StubClient(hrv=live_hrv(36)), RANGE_START, RANGE_END)
    assert all(day["signals"]["hrv"] is True for day in result["daily"])


def test_data_completeness_reports_absent_hrv(tools):
    result = tools("get_data_completeness", StubClient(hrv=None), RANGE_START, RANGE_END)
    assert all(day["signals"]["hrv"] is False for day in result["daily"])


def test_data_completeness_still_reads_the_cached_shape(tools):
    result = tools("get_data_completeness", StubClient(hrv=cached_hrv(36)), RANGE_START, RANGE_END)
    assert all(day["signals"]["hrv"] is True for day in result["daily"])


def test_period_summary_aggregates_live_hrv(tools):
    """avg_hrv is omitted entirely when no value resolves, so its presence is the assertion."""

    class WithActivities(StubClient):
        def get_activities_by_date(self, start, end, *a, **k):
            return []

    client = WithActivities(hrv=live_hrv(36))
    result = tools("get_period_summary", client, "daily", RANGE_START, True, True, True, True, True, True)
    assert result["aggregates"]["avg_hrv"] == 36.0


def test_period_summary_omits_hrv_when_absent(tools):
    class WithActivities(StubClient):
        def get_activities_by_date(self, start, end, *a, **k):
            return []

    client = WithActivities(hrv=None)
    result = tools("get_period_summary", client, "daily", RANGE_START, True, True, True, True, True, True)
    assert "avg_hrv" not in result["aggregates"]
