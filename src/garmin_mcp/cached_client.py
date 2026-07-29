"""
Read-through caching proxy around the Garmin Connect client.

Every tool module reaches Garmin through the single client handed to
`configure()`, so wrapping that one object in `main()` gives all tools cache
coverage without touching any module.

Design rules:

- Unknown attributes are passed straight through, so the ~70 uncached reads and
  every write (`add_weigh_in`, `upload_workout`, `request_reload`, ...) behave
  exactly as before.
- A cache miss, an unexpected argument shape, or any cache error falls back to
  the live client. The cache can degrade but must never break a tool.
- Dates newer than the freshness floor always go live, because the ingestor runs
  on a 6-hourly cron and Garmin keeps revising recent days.
"""

import datetime
import os

from garmin_mcp.cache import GarminCache, _as_date

# Payloads stored verbatim by the ingestor; tools cannot distinguish these from
# a live response.
EXACT_METHODS = (
    "get_sleep_data",
    "get_activities_by_date",
    "get_stats",
    "get_body_battery",
)

# Payloads the ingestor normalized or canonicalized; the reconstruction carries
# only the retained fields and is marked with `_partial`.
DERIVED_METHODS = (
    "get_rhr_day",
    "get_hrv_data",
    "get_training_readiness",
    "get_training_status",
    "get_body_composition",
)


def _env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class CachedGarminClient:
    """Wraps a Garmin client, serving settled reads from the ingestor's output."""

    def __init__(self, client, cache, enable_derived=False, verbose=False):
        self._client = client
        self._cache = cache
        self._enable_derived = enable_derived
        self._verbose = verbose
        self._enabled = set(EXACT_METHODS)
        if enable_derived:
            self._enabled.update(DERIVED_METHODS)

    def __getattr__(self, name):
        # Only reached for attributes not defined on this class, so every
        # uncached read and every write goes straight to the live client.
        return getattr(self._client, name)

    @property
    def cache_stats(self):
        return dict(self._cache.stats)

    def _log(self, message):
        if self._verbose:
            print(f"[garmin-cache] {message}")

    def _serve(self, method, day, loader, min_age_days=None):
        """Try the cache for a single-date read, else fall back to the live client."""
        if method not in self._enabled:
            return None
        parsed = _as_date(day)
        if parsed is None:
            return None
        if not self._cache.is_cacheable_date(parsed, min_age_days=min_age_days):
            self._cache._count("skip")
            return None
        try:
            result = loader(parsed)
        except Exception as exc:  # never let a cache fault break a tool
            self._cache._count("error")
            self._log(f"{method} {parsed} error: {exc}")
            return None
        if result is None:
            self._cache._count("miss")
            self._log(f"{method} {parsed} miss")
            return None
        self._cache._count("hit")
        self._log(f"{method} {parsed} hit")
        return result

    # -- exact tier -------------------------------------------------------

    def get_sleep_data(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve("get_sleep_data", cdate, self._cache.get_sleep_data)
            if cached is not None:
                return cached
        return self._client.get_sleep_data(cdate, *args, **kwargs)

    def get_stats(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve("get_stats", cdate, self._cache.get_stats)
            if cached is not None:
                return cached
        return self._client.get_stats(cdate, *args, **kwargs)

    def get_body_battery(self, startdate, enddate=None, *args, **kwargs):
        # The ingestor stores the single-day response, so only the (d, d) and
        # (d) forms can be served; wider ranges stay live.
        if not args and not kwargs and (enddate is None or enddate == startdate):
            cached = self._serve(
                "get_body_battery", startdate, self._cache.get_body_battery
            )
            if cached is not None:
                return cached
        if enddate is None:
            return self._client.get_body_battery(startdate, *args, **kwargs)
        return self._client.get_body_battery(startdate, enddate, *args, **kwargs)

    def get_activities_by_date(self, startdate, enddate, activitytype=None, *args, **kwargs):
        if not args and not kwargs:
            cached = self._activities_by_date(startdate, enddate, activitytype)
            if cached is not None:
                return cached
        return self._client.get_activities_by_date(
            startdate, enddate, activitytype, *args, **kwargs
        )

    def _activities_by_date(self, startdate, enddate, activitytype):
        if "get_activities_by_date" not in self._enabled:
            return None
        start = _as_date(startdate)
        end = _as_date(enddate)
        if start is None or end is None or start > end:
            return None
        # The whole window must be settled; a partially-ingested range would
        # silently drop recent activities.
        if not self._cache.is_cacheable_date(end):
            self._cache._count("skip")
            return None
        try:
            result = self._cache.get_activities_by_date(start, end, activitytype)
        except Exception as exc:
            self._cache._count("error")
            self._log(f"get_activities_by_date {start}..{end} error: {exc}")
            return None
        if result is None:
            self._cache._count("miss")
            self._log(f"get_activities_by_date {start}..{end} miss")
            return None
        self._cache._count("hit")
        self._log(f"get_activities_by_date {start}..{end} hit ({len(result)})")
        return result

    # -- derived tier -----------------------------------------------------

    def get_rhr_day(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve("get_rhr_day", cdate, self._cache.get_rhr_day)
            if cached is not None:
                return cached
        return self._client.get_rhr_day(cdate, *args, **kwargs)

    def get_hrv_data(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve("get_hrv_data", cdate, self._cache.get_hrv_data)
            if cached is not None:
                return cached
        return self._client.get_hrv_data(cdate, *args, **kwargs)

    def get_training_readiness(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve(
                "get_training_readiness",
                cdate,
                self._cache.get_training_readiness,
                min_age_days=2,
            )
            if cached is not None:
                return cached
        return self._client.get_training_readiness(cdate, *args, **kwargs)

    def get_training_status(self, cdate, *args, **kwargs):
        if not args and not kwargs:
            cached = self._serve(
                "get_training_status",
                cdate,
                self._cache.get_training_status,
                min_age_days=2,
            )
            if cached is not None:
                return cached
        return self._client.get_training_status(cdate, *args, **kwargs)

    def get_body_composition(self, startdate, enddate=None, *args, **kwargs):
        # Only the single-date form is cached; ranges stay live because the
        # ingestor stores one latest-of-day record per date.
        if enddate is None and not args and not kwargs:
            cached = self._serve(
                "get_body_composition", startdate, self._cache.get_body_composition
            )
            if cached is not None:
                return cached
        if enddate is None:
            return self._client.get_body_composition(startdate, *args, **kwargs)
        return self._client.get_body_composition(startdate, enddate, *args, **kwargs)


def build_cached_client(client):
    """Wrap `client` per environment config, or return it unchanged.

    Env vars:
      GARMIN_CACHE_ENABLED      enable the cache (default off)
      GARMIN_CACHE_DIR          ingestor data dir (default /data/garmin)
      GARMIN_CACHE_DB           context SQLite path; needed for activity ranges
      GARMIN_CACHE_MIN_AGE_DAYS freshness floor in days (default 1)
      GARMIN_CACHE_DERIVED      also serve lossy derived payloads (default off)
      GARMIN_CACHE_VERBOSE      log every hit/miss (default off)
    """
    if not _env_flag("GARMIN_CACHE_ENABLED"):
        return client

    data_dir = os.environ.get("GARMIN_CACHE_DIR", "/data/garmin")
    if not os.path.isdir(os.path.expanduser(data_dir)):
        print(
            f"Garmin cache enabled but data dir '{data_dir}' is not readable; "
            "continuing without cache."
        )
        return client

    db_path = os.environ.get("GARMIN_CACHE_DB")
    if db_path and not os.path.exists(os.path.expanduser(db_path)):
        print(
            f"Garmin cache DB '{db_path}' not found; activity range caching disabled."
        )
        db_path = None

    cache = GarminCache(
        data_dir=data_dir,
        db_path=db_path,
        min_age_days=_env_int("GARMIN_CACHE_MIN_AGE_DAYS", 1),
    )
    enable_derived = _env_flag("GARMIN_CACHE_DERIVED")
    tiers = "exact+derived" if enable_derived else "exact"
    print(
        f"Garmin cache enabled (dir={data_dir}, db={db_path or 'none'}, "
        f"tiers={tiers}, min_age_days={cache.min_age_days})"
    )
    return CachedGarminClient(
        client,
        cache,
        enable_derived=enable_derived,
        verbose=_env_flag("GARMIN_CACHE_VERBOSE"),
    )
