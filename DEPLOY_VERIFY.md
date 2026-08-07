# Deploy & verify prompt — garmin_mcp

Hand the block below to the agent that has server access. It deploys the branch
and runs the smallest set of checks that confirm the changes work.

**Read this first:** Garmin allows roughly **90–100 API calls per day for the
whole account**, shared with the ingestor. The verification below is designed to
spend **at most 3 live Garmin calls**. Do not add exploratory calls, do not loop
over date ranges, and do not re-run a step that already passed. If a step is
ambiguous, stop and report rather than calling again.

---

```
Repo: SteinarR/garmin_mcp
Branch to deploy: claude/registry-ajlab-uk-refs-35pnyn
Base it is built on: main @ d435594

HARD CONSTRAINT — READ BEFORE ANY TOOL CALL
Garmin rate-limits the whole account to roughly 90-100 API calls per day, and
that budget is shared with the garmin-ingestor. Everything below is scoped to
a maximum of 3 live Garmin calls total. Rules:
  - Make ONLY the calls listed in step 4. No exploratory calls.
  - Never call a range tool (get_trends, detect_anomalies, get_period_summary,
    get_optimized_health_data, get_coach_cues) during verification. They cost
    5-7 calls per day of range.
  - If a call fails, do NOT retry it. Record the error and move on.
  - If you need information you could get either from a log or from an API
    call, use the log.
Report your total live-call count at the end.

WHAT CHANGED (three commits, all on the branch above)

  e3228d8  get_readiness_breakdown: HRV component was dead on live data and
           the scale was miscalibrated.
  d155831  The same HRV bug at four more call sites: get_trends,
           detect_anomalies, get_data_completeness, get_period_summary.
  e1fb8fd  The cache now warns when a read-only mount silently disables it.
           Plus docs: API budget rules, and the get_hrv_data note closed out.

The root cause across the first two: live Garmin nests overnight HRV at
hrvSummary.lastNightAvg, but the code read the flat keys avgHrv/average that
only the ingested-data cache produces. HRV silently resolved to None on every
live call while looking correct against cached dates.

STEP 1 — DEPLOY
Deploy the branch however this server normally deploys. Confirm the running
container is on commit e1fb8fd before continuing. Note: the build/deploy path
is NOT docker.sh (that file was deleted; it pointed at the wrong registry).

STEP 2 — CONFIRM THE CACHE MOUNT (0 Garmin calls)
Check the startup logs for either of these:

  [garmin-cache] WARNING: cannot open '<db>' because its directory is
  read-only. ...

  Garmin cache enabled (dir=..., db=..., tiers=..., min_age_days=...)

If you see the WARNING line, the context-DB directory is mounted read-only and
activity range caching is OFF — every range query is burning the API budget.
Fix: mount the directory holding the context DB READ-WRITE. The connection
itself stays mode=ro, so the server still cannot write to the database. The
data directory (GARMIN_CACHE_DIR) is genuinely read-only and should stay :ro.

Important: the absence of the warning at startup does not prove the mount is
right. The warning only fires on the first query that touches the DB. Trigger
it with step 3, which costs nothing.

STEP 3 — EXERCISE THE CACHE PATH (0 Garmin calls)
Call get_activities_by_date for a SETTLED range that the cache can serve — a
2-day range at least a week in the past. This reads from the ingestor's SQLite
index, not from Garmin.

Then re-check the logs for the [garmin-cache] WARNING line. If it appears now,
the mount is wrong; apply the fix from step 2 and redeploy.

STEP 4 — THE LIVE CHECKS (3 Garmin calls, maximum)
Pick ONE settled date (at least 3 days ago, so the cache and Garmin both have
it). Use the SAME date for all three calls. Call each exactly once.

  4a. get_hrv_data(<date>)
      Expect: a JSON string, no error.
      This closes an open question in TOOLS.md: a Pydantic validation error
      ("Input should be a valid string", receiving a dict) was reported some
      time ago. Code inspection says it cannot happen anymore, but it has never
      been confirmed live. Record the outcome either way — it is the whole
      point of this call.

  4b. get_readiness_breakdown(<date>)
      Expect these fields, which are new:
        hrv_scoring_method       one of: garmin_hrv_factor,
                                 personal_baseline,
                                 population_scale_approximate
        hrv_ms                   the overnight HRV in ms, NOT null
        components_used          should contain "hrv_score"
        components_missing       should NOT contain "hrv_score"
        garmin_training_readiness  Garmin's own score, for comparison
      THE KEY ASSERTION: components.hrv_score must not be null. Before this
      fix it was null on every live call. If it is null, the fix did not take
      or the deploy is on the wrong commit.
      Note this tool now makes an extra internal call to get_training_readiness
      for Garmin's own HRV factor, so it costs ~5 Garmin calls on an uncached
      date. Using a settled date keeps most of that on the cache.

  4c. get_readiness_breakdown("today")
      Expect: hrv_score still not null.
      This is the real regression test. Today is never served from cache, so
      this is the pure live path — exactly the case that was broken. If 4b
      passes and 4c fails, the live HRV shape differs from what the fix
      expects; capture the raw get_hrv_data payload shape from the logs (do
      NOT make another call) and report it.

DO NOT RUN
  - Any range tool. get_trends is separately broken upstream anyway.
  - get_sleep_data through MCP. It returns ~280,000 characters and exceeds the
    MCP result limit; it will fail and waste a call.
  - Any retry of a failed call.

REPORT BACK
  1. Commit actually deployed.
  2. Whether the [garmin-cache] WARNING appeared, before and after step 3.
  3. For 4a: did it return cleanly? This closes the TOOLS.md note either way.
  4. For 4b and 4c: hrv_score, hrv_ms, hrv_scoring_method, components_missing,
     and garmin_training_readiness for each.
  5. Your total live Garmin call count.

If everything passes, say so plainly and note that TOOLS.md's get_hrv_data
note can now be deleted.
```

---

## Why each step is scoped this way

**Steps 2 and 3 cost nothing.** The read-only-mount failure is invisible by
design — a read-only mount works for as long as some other connection keeps
`-wal`/`-shm` alive on disk, then starts failing once they are gone. Reproduced
against a real WAL database:

| Directory | `-shm` on disk | Result |
|---|---|---|
| writable | created on open | works |
| **read-only** | **still present** | **works — this is the trap** |
| read-only | absent | `SQLITE_READONLY_DIRECTORY` |

So the mount must be exercised, not inspected. Step 3 does that against the
cache, with no Garmin traffic.

**Step 4c is the one that matters.** The bug only ever showed on live data;
against settled dates the cache flattens HRV to the key the old code expected,
so the defect disappeared exactly when you tested for it. A cached date passing
proves very little on its own — hence a settled date and today, in that order.

**`get_hrv_data` is one call, not a retry loop.** The original report described
an *intermittent* error that succeeded on retry, which invites re-running it.
Don't. `training.py:114-126` returns `_to_json_str(...)` on every branch, so the
reported dict-instead-of-string error is structurally impossible now; a single
clean call is sufficient evidence.
