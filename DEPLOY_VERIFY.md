# Verifying a deploy

Standing rules for checking a `garmin_mcp` deploy on the server. Release-specific
steps belong in the pull request being verified, not here — an earlier version of
this file was a hand-off prompt for one release and was stale within days,
pointing at a branch that no longer existed.

## The budget comes first

Garmin rate-limits the whole account to roughly **90-100 calls per day**, shared
with the garmin-ingestor. It is the binding constraint on everything this server
does, and on how it gets tested.

State a call budget before starting, and make it honest. The first version of
this document set a hard cap of 3 live calls and then asked for a check costing
5. The agent running it correctly refused — which meant the only check that
exercised the actual defect never ran, and the release was reported as verified
on the strength of checks that could not have failed.

Rules that hold for any release:

- **Never call a range tool to verify anything.** `get_trends`,
  `detect_anomalies`, `get_period_summary`, `get_optimized_health_data` and
  `get_coach_cues` cost 5-7 calls *per day of range*.
- **Never call `get_sleep_data` through MCP.** ~280,000 characters, over the
  result limit; it fails and wastes the call.
- **Never retry a failed call.** Record the error and move on.
- **Prefer a file or a log over a call**, always.
- **Report the actual live-call count** at the end.

## A cached date proves less than you think

This is the trap that has caught two releases. The ingested-data cache serves
settled dates from disk, and its payload shapes differ from live Garmin's. A
defect in code that reads live payloads is *invisible* against a cached date —
the cache happens to produce the key the broken code expected.

So for anything touching payload parsing:

- **A settled-date check confirms nothing regressed.** It does not confirm a
  live-path fix works.
- **`"today"` is the real test.** It is never served from cache, so every input
  is live. It costs more, and it is the only thing that exercises the path.

If the budget only allows one, make it `"today"`.

## Zero-cost checks to run every time

These need no Garmin calls and catch the failures that matter most.

**The commit actually running.** Report it. Deploy the branch tip or the merge
commit, not an intermediate one — a previous run pinned a mid-branch commit and
missed later fixes.

**The cache mount.** Look for either line at startup:

```
Garmin cache enabled (dir=..., db=..., tiers=..., min_age_days=...)
[garmin-cache] WARNING: cannot open '<db>' ... directory is read-only
```

The warning means the context-DB directory is mounted read-only, activity range
caching is off, and every range query is spending budget. Fix: mount the
directory holding the context DB **read-write**. The connection itself stays
`mode=ro`, so the server still cannot write to the database; `GARMIN_CACHE_DIR`
stays `:ro`.

Absence of the warning at startup proves nothing — it fires on the first query
that touches the DB. Trigger it deliberately.

**The lockfile.** Compare `/app/uv.lock` in the container against the committed
one. They must be byte-identical. A `uv` older than lockfile `revision` support
silently rewrites it during `uv sync --frozen`, which means the built image does
not match the lock.

**What the ingestor is actually writing.** Reading a stored payload costs
nothing and answers questions no API call can:

```bash
python3 -c "import json;d=json.load(open('/data/garmin/raw/stats/<date>.json'));print(sorted(d))"
grep -l trainingReadinessRaw /data/garmin/raw/daily_training_state/*.json | head
```

Remember that an ingestor change only takes effect for payloads written **after
that service is redeployed**, and only for days written from then on. A
committed change is not a live one.

## Exercising the cache is not free by default

The cache is **fail-open**: a DB error or a missing raw file falls back to the
live API. So a "cached" call is only zero-cost if you check first.

Before calling `get_activities_by_date` on a settled range, confirm on the
server that the SQLite rows exist for it *and* that every referenced raw
activity file is present. Then call it, then re-check the logs for the warning.

## Freshness floors, when reading results

A result that looks wrong is often just a date that is too recent:

- Settled dates are servable once older than `GARMIN_CACHE_MIN_AGE_DAYS`
  (default 1).
- **Training readiness and status use a stricter 2-day floor.** A day carrying
  a newly-added field is not servable from cache until it has aged past it.
  That does *not* mean a fresh ingestor change takes two days to observe: the
  ingestor re-fetches a rolling window, so its first run after deployment
  rewrites roughly a week of days at once, most of them already past the floor.
  Check what the run actually wrote before concluding a change has not landed.
- `get_stress_data` is never cached, for any date. It is why even a fully
  cached `get_readiness_breakdown` still costs one live call.

## Reading `get_readiness_breakdown`

The most informative single call, and the one worth spending budget on. Check:

- `components_missing` — empty is the goal. A named component here is a real
  finding; this field is what surfaced the body-battery defect in production.
- `hrv_scoring_method` — must be consistent with what is on disk. On `"today"`
  expect `garmin_hrv_factor`. On a settled date expect
  `stored_history_approximate` unless that day carries a raw training-readiness
  block, in which case expect `garmin_hrv_factor` there too.
  `population_scale_approximate` means neither was available — report it, it is
  informative rather than wrong.
- `hrv_baseline_samples` — how many nights backed a history-derived score.
- `garmin_training_readiness` — Garmin's own score, for comparison with the
  composite.
