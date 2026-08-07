"""
Read-through cache backed by personal-ai's garmin-ingestor output.

The ingestor (personal-ai/services/garmin-ingestor) runs on a 6-hourly cron and
persists Garmin payloads to a data directory plus an optional SQLite context DB.
When the MCP server is co-located with that data, most per-date reads can be
served from disk instead of spending calls against the ~90-100/day API budget.

Two fidelity tiers, enabled independently:

- exact:   the stored payload is byte-identical to what the Garmin client
           returned, so tools cannot tell the difference. Covers sleep and
           activities.
- derived: the stored payload is a lossy projection (the ingestor normalizes or
           canonicalizes it), so the reconstructed response carries only the
           fields the ingestor kept. Covers resting HR, HRV, training
           status/readiness and body composition.

Anything not listed here is passed straight through to the live client.
"""

import datetime
import json
import os
import sqlite3
import threading
from pathlib import Path

# Marker keys added to derived-tier responses so a partial payload is never
# mistaken for a full Garmin response.
SOURCE_KEY = "_source"
PARTIAL_KEY = "_partial"
SOURCE_VALUE = "garmin-ingestor-cache"

# The ingestor re-fetches the most recent days because Garmin recomputes
# training state as overnight and activity data lands. Never serve those from
# cache regardless of the configured floor.
TRAINING_STATE_MIN_AGE_DAYS = 2

# Window used to build a personal HRV baseline from stored sleep payloads.
# Roughly matches the span Garmin's own baseline covers, and each day costs one
# large JSON parse, so results are memoised.
HRV_HISTORY_DAYS = 60
HRV_HISTORY_MEMO_MAX = 32


def _default_warning(message):
    print(f"[garmin-cache] WARNING: {message}")


def _is_readonly_directory_error(exc):
    """True when SQLite failed because it cannot write beside the database.

    Opening a WAL database needs a `-shm` file in the database's directory. A
    read-only mount cannot create one, and SQLite reports that as
    SQLITE_READONLY_DIRECTORY. This is worth singling out because it looks like
    a working mount right up until it isn't: `-wal` and `-shm` survive on disk
    only while some connection holds them open, so a read-only mount reuses the
    files another container left behind and reads fine. Stop that container
    while nothing else is connected, the files go away, and every query here
    starts failing — silently, as a fallback to the live Garmin API.
    """
    # sqlite3 sets sqlite_errorname only on exceptions it raises itself; one
    # constructed by hand (a test, a re-raise) carries the message and nothing
    # else. Hence the fallback — it is not about Python version support.
    name = getattr(exc, "sqlite_errorname", None)
    if name is not None:
        return name == "SQLITE_READONLY_DIRECTORY"
    return "attempt to write a readonly database" in str(exc)


def _as_date(value):
    """Coerce a date, datetime or YYYY-MM-DD string to a date. None if invalid."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


class GarminCache:
    """Reads ingested Garmin payloads from disk and the context SQLite DB."""

    def __init__(self, data_dir, db_path=None, min_age_days=1, on_warning=None):
        self.data_dir = Path(os.path.expanduser(str(data_dir)))
        self.db_path = Path(os.path.expanduser(str(db_path))) if db_path else None
        self.min_age_days = max(0, int(min_age_days))
        self._lock = threading.Lock()
        self.stats = {"hit": 0, "miss": 0, "skip": 0, "error": 0}
        # Deliberately not gated on GARMIN_CACHE_VERBOSE: these warn about
        # misconfiguration that is otherwise invisible, and verbose is meant to
        # stay off in normal operation.
        self._on_warning = on_warning if callable(on_warning) else _default_warning
        self._warned = set()
        self._hrv_history_memo = {}

    # -- bookkeeping ------------------------------------------------------

    def _count(self, outcome):
        with self._lock:
            self.stats[outcome] = self.stats.get(outcome, 0) + 1

    def _warn_once(self, key, message):
        """Emit `message` the first time `key` is seen. Queries repeat; this must not."""
        with self._lock:
            if key in self._warned:
                return
            self._warned.add(key)
        self._on_warning(message)

    def is_cacheable_date(self, day, min_age_days=None):
        """True when `day` is old enough that the ingestor has settled data for it."""
        day = _as_date(day)
        if day is None:
            return False
        floor = self.min_age_days if min_age_days is None else max(self.min_age_days, min_age_days)
        return day <= datetime.date.today() - datetime.timedelta(days=floor)

    # -- raw file access --------------------------------------------------

    def _read_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def read_raw(self, category, name):
        """Read data_dir/raw/<category>/<name>.json, or None if absent/unreadable."""
        return self._read_json(self.data_dir / "raw" / category / f"{name}.json")

    def _resolve_stored_path(self, stored):
        """Resolve a raw_path/normalized_path column, which may be relative or absolute."""
        if not stored:
            return None
        path = Path(stored)
        return path if path.is_absolute() else self.data_dir / path

    # -- sqlite access ----------------------------------------------------

    def _query(self, sql, params=()):
        """Run a read-only query. Returns [] when the DB is unavailable."""
        if not self.db_path or not self.db_path.exists():
            return []
        conn = None
        try:
            # mode=ro guarantees this process can never write to the DB the
            # ingestor owns; WAL lets us read while a sync is in flight. Note
            # that WAL still needs to create a -shm file next to the database,
            # so the containing directory must be mounted read-write even
            # though this connection is read-only.
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro", uri=True, timeout=5.0
            )
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            self._count("error")
            if _is_readonly_directory_error(exc):
                self._warn_once(
                    "readonly_directory",
                    f"cannot open '{self.db_path}' because its directory is "
                    "read-only. SQLite needs to create a -shm file next to a WAL "
                    "database. Activity range caching is OFF and every range "
                    "query is going to the live Garmin API instead. Mount the "
                    "directory holding the context DB read-write; the connection "
                    "itself stays mode=ro, so this server still cannot write to "
                    "the database.",
                )
            else:
                self._warn_once(
                    "sqlite_error",
                    f"query against '{self.db_path}' failed ({exc}). Activity "
                    "range caching is falling back to the live Garmin API.",
                )
            return []
        finally:
            if conn is not None:
                conn.close()

    # -- exact tier -------------------------------------------------------

    def get_sleep_data(self, day):
        """Exact: the ingestor stores the unmodified get_sleep_data payload."""
        payload = self.read_raw("sleep", day.isoformat())
        return payload if isinstance(payload, dict) else None

    def get_stats(self, day):
        """Exact: the ingestor stores the unmodified get_stats payload."""
        payload = self.read_raw("stats", day.isoformat())
        return payload if isinstance(payload, dict) else None

    def get_body_battery(self, day):
        """Exact: stored from get_body_battery(day, day), so single-day only."""
        payload = self.read_raw("body_battery", day.isoformat())
        return payload if isinstance(payload, list) else None

    def get_activities_by_date(self, start, end, activity_type=None):
        """Exact per activity: look up ids in SQLite, then read each raw payload."""
        rows = self._query(
            """
            SELECT garmin_activity_id, raw_path
            FROM activity_records
            WHERE date(start_time) BETWEEN ? AND ?
            ORDER BY start_time DESC
            """,
            (start.isoformat(), end.isoformat()),
        )
        if not rows:
            return None

        activities = []
        for row in rows:
            payload = None
            resolved = self._resolve_stored_path(row["raw_path"])
            if resolved is not None:
                payload = self._read_json(resolved)
            if payload is None:
                payload = self.read_raw("activities", str(row["garmin_activity_id"]))
            if payload is None:
                # A retained DB row with no raw file means the cached range would
                # silently omit an activity. Fall back to the live API instead.
                return None
            activities.append(payload)

        if activity_type:
            wanted = str(activity_type).strip().lower()
            activities = [a for a in activities if _activity_type_of(a) == wanted]
        return activities

    # -- derived tier -----------------------------------------------------

    def get_rhr_day(self, day):
        """Derived from raw sleep: restingHeartRate is the only field tools read."""
        payload = self.get_sleep_data(day)
        if not payload:
            return None
        value = payload.get("restingHeartRate")
        if value is None:
            return None
        return {
            "restingHeartRate": value,
            "calendarDate": day.isoformat(),
            SOURCE_KEY: SOURCE_VALUE,
            PARTIAL_KEY: True,
        }

    def get_hrv_data(self, day):
        """Derived from raw sleep: overnight HRV summary, not the full HRV feed."""
        payload = self.get_sleep_data(day)
        if not payload:
            return None
        avg = payload.get("avgOvernightHrv")
        status = payload.get("hrvStatus")
        if avg is None and status is None:
            return None
        result = {
            "avgHrv": avg,
            "average": avg,
            "hrvStatus": status,
            "calendarDate": day.isoformat(),
            SOURCE_KEY: SOURCE_VALUE,
            PARTIAL_KEY: True,
        }
        if isinstance(payload.get("hrvData"), list):
            result["hrvReadings"] = payload["hrvData"]
        return result

    def hrv_history(self, end_day, days=HRV_HISTORY_DAYS):
        """Overnight HRV values from the stored sleep payloads, oldest first.

        Reads disk and nothing else. There is deliberately no live fallback:
        callers use this to build a personal baseline, and quietly turning that
        into `days` Garmin requests would blow the daily API budget outright.

        Days with no stored payload are skipped rather than interpolated, so a
        gappy window yields fewer values instead of wrong ones.
        """
        end_day = _as_date(end_day)
        if end_day is None:
            return []
        days = max(1, int(days))
        key = (end_day.isoformat(), days)
        with self._lock:
            hit = self._hrv_history_memo.get(key)
        if hit is not None:
            return list(hit)

        values = []
        # Start at the day before `end_day`: a baseline should not include the
        # night it is being used to judge.
        for offset in range(1, days + 1):
            day = end_day - datetime.timedelta(days=offset)
            payload = self.read_raw("sleep", day.isoformat())
            if not isinstance(payload, dict):
                continue
            value = payload.get("avgOvernightHrv")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            values.append(float(value))
        values.reverse()

        with self._lock:
            # Each entry parses up to `days` sleep payloads, which are large.
            # Bound the memo rather than let a long-lived process accumulate one
            # entry per date ever queried.
            if len(self._hrv_history_memo) >= HRV_HISTORY_MEMO_MAX:
                self._hrv_history_memo.clear()
            self._hrv_history_memo[key] = list(values)
        return values

    def _daily_training_state(self, day):
        payload = self.read_raw("daily_training_state", day.isoformat())
        return payload if isinstance(payload, dict) else None

    def get_training_readiness(self, day):
        """Derived: the ingestor keeps only the trainingReadiness scalar."""
        payload = self._daily_training_state(day)
        if not payload or payload.get("trainingReadiness") is None:
            return None
        return {
            "score": payload["trainingReadiness"],
            "trainingReadiness": payload["trainingReadiness"],
            "calendarDate": payload.get("calendarDate", day.isoformat()),
            SOURCE_KEY: SOURCE_VALUE,
            PARTIAL_KEY: True,
        }

    def get_training_status(self, day):
        """Derived: training status code plus the acute/chronic load figures."""
        payload = self._daily_training_state(day)
        if not payload or payload.get("trainingStatusCode") is None:
            return None
        return {
            "trainingStatusCode": payload["trainingStatusCode"],
            "acuteLoad": payload.get("acuteLoad"),
            "chronicLoad": payload.get("chronicLoad"),
            "loadRatio": payload.get("loadRatio"),
            "calendarDate": payload.get("calendarDate", day.isoformat()),
            SOURCE_KEY: SOURCE_VALUE,
            PARTIAL_KEY: True,
        }

    def get_body_composition(self, day):
        """Derived: the ingestor already converted to kg, so convert back to grams.

        Garmin returns `weight` and `muscleMass` in grams and callers divide by
        1000 themselves. Emitting the stored kg value here would understate
        weight by a factor of 1000.
        """
        payload = self.read_raw("body_metrics", day.isoformat())
        if not isinstance(payload, dict):
            return None
        weight_kg = payload.get("weightKg")
        muscle_kg = payload.get("muscleMassKg")
        body_fat = payload.get("bodyFatPercent")
        if weight_kg is None and muscle_kg is None and body_fat is None:
            return None
        return [
            {
                "calendarDate": payload.get("calendarDate", day.isoformat()),
                "weight": weight_kg * 1000.0 if weight_kg is not None else None,
                "muscleMass": muscle_kg * 1000.0 if muscle_kg is not None else None,
                "bodyFat": body_fat,
                SOURCE_KEY: SOURCE_VALUE,
                PARTIAL_KEY: True,
            }
        ]


def _activity_type_of(activity):
    """Best-effort activity type key, matching how the MCP filters by type."""
    if not isinstance(activity, dict):
        return None
    type_field = activity.get("activityType")
    if isinstance(type_field, dict):
        key = type_field.get("typeKey")
        if key:
            return str(key).lower()
    for key in ("typeKey", "type"):
        if activity.get(key):
            return str(activity[key]).lower()
    return None
