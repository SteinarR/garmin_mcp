"""
Tests for the garmin-ingestor read-through cache.

These run without Garmin credentials or network access: the live client is a
recording stub, and the ingestor layout is built in a tmp_path fixture.
"""

import datetime
import json
import sqlite3

import pytest

from garmin_mcp.cache import GarminCache
from garmin_mcp.cached_client import CachedGarminClient, build_cached_client


TODAY = datetime.date.today()
SETTLED = TODAY - datetime.timedelta(days=5)
RECENT = TODAY


class FakeClient:
    """Stands in for the Garmin client, recording every call it receives."""

    def __init__(self):
        self.calls = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return {"live": name}

    def get_sleep_data(self, cdate, *a, **k):
        return self._record("get_sleep_data", cdate, *a, **k)

    def get_activities_by_date(self, s, e, t=None, *a, **k):
        return self._record("get_activities_by_date", s, e, t, *a, **k)

    def get_rhr_day(self, cdate, *a, **k):
        return self._record("get_rhr_day", cdate, *a, **k)

    def get_hrv_data(self, cdate, *a, **k):
        return self._record("get_hrv_data", cdate, *a, **k)

    def get_training_readiness(self, cdate, *a, **k):
        return self._record("get_training_readiness", cdate, *a, **k)

    def get_training_status(self, cdate, *a, **k):
        return self._record("get_training_status", cdate, *a, **k)

    def get_body_composition(self, s, e=None, *a, **k):
        return self._record("get_body_composition", s, e, *a, **k)

    def get_stats(self, cdate, *a, **k):
        return self._record("get_stats", cdate, *a, **k)

    def get_body_battery(self, s, e=None, *a, **k):
        return self._record("get_body_battery", s, e, *a, **k)

    def get_max_metrics(self, cdate):
        return self._record("get_max_metrics", cdate)

    def add_weigh_in(self, weight):
        return self._record("add_weigh_in", weight)

    def get_activities(self, start, limit):
        return self._record("get_activities", start, limit)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def data_dir(tmp_path):
    """An ingestor data directory with one settled day of every category."""
    root = tmp_path / "garmin"
    day = SETTLED.isoformat()

    _write(
        root / "raw" / "sleep" / f"{day}.json",
        {
            "dailySleepDTO": {"calendarDate": day, "sleepTimeSeconds": 27000},
            "restingHeartRate": 48,
            "avgOvernightHrv": 62,
            "hrvStatus": "BALANCED",
            "hrvData": [{"value": 60}],
        },
    )
    _write(
        root / "raw" / "daily_training_state" / f"{day}.json",
        {
            "calendarDate": day,
            "acuteLoad": 300,
            "chronicLoad": 280,
            "loadRatio": 1.07,
            "trainingStatusCode": "PRODUCTIVE",
            "trainingReadiness": 71,
        },
    )
    _write(
        root / "raw" / "body_metrics" / f"{day}.json",
        {
            "calendarDate": day,
            "weightKg": 80.5,
            "muscleMassKg": 35.0,
            "bodyFatPercent": 18.2,
        },
    )
    _write(
        root / "raw" / "stats" / f"{day}.json",
        {"calendarDate": day, "totalSteps": 11542, "restingHeartRate": 47},
    )
    _write(
        root / "raw" / "body_battery" / f"{day}.json",
        [{"date": day, "bodyBatteryValuesArray": [[0, "MEASURED", 55, 1.0]]}],
    )
    _write(
        root / "raw" / "activities" / "111.json",
        {"activityId": 111, "activityType": {"typeKey": "running"}},
    )
    _write(
        root / "raw" / "activities" / "222.json",
        {"activityId": 222, "activityType": {"typeKey": "cycling"}},
    )
    return root


@pytest.fixture
def db_path(tmp_path, data_dir):
    """A context DB with activity rows pointing at the raw files."""
    path = tmp_path / "context_kernel.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE activity_records (
            garmin_activity_id TEXT PRIMARY KEY,
            start_time TEXT,
            raw_path TEXT,
            normalized_path TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO activity_records VALUES (?,?,?,?)",
        [
            ("111", f"{SETTLED.isoformat()}T06:00:00", "raw/activities/111.json", ""),
            ("222", f"{SETTLED.isoformat()}T18:00:00", "raw/activities/222.json", ""),
        ],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def client(data_dir, db_path):
    cache = GarminCache(data_dir=data_dir, db_path=db_path, min_age_days=1)
    live = FakeClient()
    return CachedGarminClient(live, cache, enable_derived=True), live


# -- exact tier -----------------------------------------------------------


def test_sleep_served_from_cache_verbatim(client):
    cached, live = client
    result = cached.get_sleep_data(SETTLED.isoformat())
    assert result["dailySleepDTO"]["sleepTimeSeconds"] == 27000
    # Exact tier must not add markers; the payload is byte-identical.
    assert "_source" not in result
    assert live.calls == []


def test_recent_date_bypasses_cache(client):
    cached, live = client
    cached.get_sleep_data(RECENT.isoformat())
    assert [c[0] for c in live.calls] == ["get_sleep_data"]


def test_missing_day_falls_back_to_live(client):
    cached, live = client
    absent = (SETTLED - datetime.timedelta(days=30)).isoformat()
    assert cached.get_sleep_data(absent) == {"live": "get_sleep_data"}
    assert live.calls[0][0] == "get_sleep_data"


def test_activities_by_date_from_db_index(client):
    cached, live = client
    result = cached.get_activities_by_date(SETTLED.isoformat(), SETTLED.isoformat())
    assert [a["activityId"] for a in result] == [222, 111]  # start_time DESC
    assert live.calls == []


def test_activities_filtered_by_type(client):
    cached, _ = client
    result = cached.get_activities_by_date(
        SETTLED.isoformat(), SETTLED.isoformat(), "running"
    )
    assert [a["activityId"] for a in result] == [111]


def test_activity_range_ending_recent_goes_live(client):
    cached, live = client
    cached.get_activities_by_date(SETTLED.isoformat(), RECENT.isoformat())
    assert live.calls[0][0] == "get_activities_by_date"


def test_db_row_without_raw_file_falls_back(tmp_path, data_dir, db_path):
    (data_dir / "raw" / "activities" / "111.json").unlink()
    cache = GarminCache(data_dir=data_dir, db_path=db_path, min_age_days=1)
    live = FakeClient()
    cached = CachedGarminClient(live, cache)
    # A partial range would silently drop an activity, so it must go live.
    cached.get_activities_by_date(SETTLED.isoformat(), SETTLED.isoformat())
    assert live.calls[0][0] == "get_activities_by_date"


# -- derived tier ---------------------------------------------------------


def test_rhr_derived_from_sleep(client):
    cached, live = client
    result = cached.get_rhr_day(SETTLED.isoformat())
    assert result["restingHeartRate"] == 48
    assert result["_partial"] is True
    assert live.calls == []


def test_hrv_derived_exposes_both_field_names(client):
    cached, _ = client
    result = cached.get_hrv_data(SETTLED.isoformat())
    # Callers read `avgHrv` or `average`; both must be populated.
    assert result["avgHrv"] == 62
    assert result["average"] == 62


def test_training_state_respects_stricter_floor(data_dir):
    # Two days old is inside the ingestor's recompute window at floor=1.
    cache = GarminCache(data_dir=data_dir, db_path=None, min_age_days=1)
    live = FakeClient()
    cached = CachedGarminClient(live, cache, enable_derived=True)
    recent = (TODAY - datetime.timedelta(days=1)).isoformat()
    cached.get_training_readiness(recent)
    assert live.calls[0][0] == "get_training_readiness"


def test_training_readiness_served_when_settled(client):
    cached, live = client
    result = cached.get_training_readiness(SETTLED.isoformat())
    assert result["score"] == 71
    assert live.calls == []


def test_body_composition_converted_back_to_grams(client):
    cached, _ = client
    result = cached.get_body_composition(SETTLED.isoformat())
    # The ingestor stores kg; callers expect Garmin's grams.
    assert result[0]["weight"] == 80500.0
    assert result[0]["muscleMass"] == 35000.0


def test_body_composition_range_stays_live(client):
    cached, live = client
    cached.get_body_composition(SETTLED.isoformat(), SETTLED.isoformat())
    assert live.calls[0][0] == "get_body_composition"


def test_derived_disabled_by_default(data_dir, db_path):
    cache = GarminCache(data_dir=data_dir, db_path=db_path, min_age_days=1)
    live = FakeClient()
    cached = CachedGarminClient(live, cache)  # exact tier only
    cached.get_rhr_day(SETTLED.isoformat())
    assert live.calls[0][0] == "get_rhr_day"


# -- passthrough ----------------------------------------------------------


def test_stats_served_from_cache_verbatim(client):
    cached, live = client
    result = cached.get_stats(SETTLED.isoformat())
    assert result["totalSteps"] == 11542
    assert "_source" not in result
    assert live.calls == []


def test_body_battery_single_day_served_from_cache(client):
    cached, live = client
    result = cached.get_body_battery(SETTLED.isoformat(), SETTLED.isoformat())
    assert result[0]["bodyBatteryValuesArray"][0][2] == 55
    assert live.calls == []


def test_body_battery_range_stays_live(client):
    cached, live = client
    earlier = (SETTLED - datetime.timedelta(days=3)).isoformat()
    cached.get_body_battery(earlier, SETTLED.isoformat())
    assert live.calls[0][0] == "get_body_battery"


def test_uncached_read_passes_through(client):
    cached, live = client
    cached.get_max_metrics(SETTLED.isoformat())
    assert live.calls[0][0] == "get_max_metrics"


def test_write_methods_pass_through(client):
    cached, live = client
    cached.add_weigh_in(80)
    assert live.calls[0] == ("add_weigh_in", (80,), {})


def test_get_activities_is_never_cached(client):
    cached, live = client
    # Inherently "most recent", so it always needs live data.
    cached.get_activities(0, 5)
    assert live.calls[0][0] == "get_activities"


def test_cache_error_falls_back(client, monkeypatch):
    cached, live = client

    def boom(_day):
        raise RuntimeError("corrupt cache")

    monkeypatch.setattr(cached._cache, "get_sleep_data", boom)
    assert cached.get_sleep_data(SETTLED.isoformat()) == {"live": "get_sleep_data"}
    assert cached.cache_stats["error"] == 1


def test_bad_date_string_falls_back(client):
    cached, live = client
    cached.get_sleep_data("not-a-date")
    assert live.calls[0][0] == "get_sleep_data"


def test_missing_db_disables_activity_cache_only(data_dir):
    cache = GarminCache(data_dir=data_dir, db_path=None, min_age_days=1)
    live = FakeClient()
    cached = CachedGarminClient(live, cache, enable_derived=True)
    cached.get_activities_by_date(SETTLED.isoformat(), SETTLED.isoformat())
    assert live.calls[0][0] == "get_activities_by_date"
    # Sleep still comes from disk.
    assert cached.get_sleep_data(SETTLED.isoformat())["restingHeartRate"] == 48


# -- wiring ---------------------------------------------------------------


# -- verbose logging ------------------------------------------------------
#
# Every cache decision must leave a line when verbose is on. A silent bypass is
# indistinguishable from a broken cache to anyone reading the logs.


@pytest.fixture
def verbose_client(data_dir, db_path, capsys):
    cache = GarminCache(data_dir=data_dir, db_path=db_path, min_age_days=1)
    live = FakeClient()
    cached = CachedGarminClient(live, cache, enable_derived=True, verbose=True)
    return cached, capsys


def test_verbose_logs_hit(verbose_client):
    cached, capsys = verbose_client
    cached.get_sleep_data(SETTLED.isoformat())
    assert "hit" in capsys.readouterr().out


def test_verbose_logs_miss(verbose_client):
    cached, capsys = verbose_client
    absent = (SETTLED - datetime.timedelta(days=30)).isoformat()
    cached.get_sleep_data(absent)
    assert "miss" in capsys.readouterr().out


def test_verbose_logs_skip_on_recent_date(verbose_client):
    cached, capsys = verbose_client
    cached.get_sleep_data(RECENT.isoformat())
    out = capsys.readouterr().out
    assert "skip" in out
    assert "freshness floor" in out


def test_verbose_logs_skip_on_recent_activity_range(verbose_client):
    cached, capsys = verbose_client
    cached.get_activities_by_date(SETTLED.isoformat(), RECENT.isoformat())
    out = capsys.readouterr().out
    assert "skip" in out


def test_verbose_logs_bypass_on_body_battery_range(verbose_client):
    cached, capsys = verbose_client
    earlier = (SETTLED - datetime.timedelta(days=3)).isoformat()
    cached.get_body_battery(earlier, SETTLED.isoformat())
    assert "bypass" in capsys.readouterr().out


def test_verbose_logs_bypass_on_body_composition_range(verbose_client):
    cached, capsys = verbose_client
    cached.get_body_composition(SETTLED.isoformat(), SETTLED.isoformat())
    assert "bypass" in capsys.readouterr().out


def test_verbose_logs_bypass_on_bad_date(verbose_client):
    cached, capsys = verbose_client
    cached.get_sleep_data("not-a-date")
    assert "bypass" in capsys.readouterr().out


def test_quiet_by_default(client, capsys):
    cached, _ = client
    cached.get_sleep_data(SETTLED.isoformat())
    assert "garmin-cache" not in capsys.readouterr().out


def test_skip_is_counted_as_well_as_logged(verbose_client):
    cached, _ = verbose_client
    cached.get_sleep_data(RECENT.isoformat())
    assert cached.cache_stats["skip"] == 1


def test_build_returns_client_unchanged_when_disabled(monkeypatch, data_dir):
    monkeypatch.delenv("GARMIN_CACHE_ENABLED", raising=False)
    live = FakeClient()
    assert build_cached_client(live) is live


def test_build_wraps_when_enabled(monkeypatch, data_dir, db_path):
    monkeypatch.setenv("GARMIN_CACHE_ENABLED", "true")
    monkeypatch.setenv("GARMIN_CACHE_DIR", str(data_dir))
    monkeypatch.setenv("GARMIN_CACHE_DB", str(db_path))
    live = FakeClient()
    wrapped = build_cached_client(live)
    assert isinstance(wrapped, CachedGarminClient)
    assert wrapped.get_sleep_data(SETTLED.isoformat())["restingHeartRate"] == 48


def test_build_degrades_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CACHE_ENABLED", "true")
    monkeypatch.setenv("GARMIN_CACHE_DIR", str(tmp_path / "nope"))
    live = FakeClient()
    assert build_cached_client(live) is live
