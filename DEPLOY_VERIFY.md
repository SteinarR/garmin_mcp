# Deploy & verify prompt — garmin_mcp

Hand the block below to the agent that has server access.

**Budget note, corrected.** An earlier version of this file set a hard limit of
3 live Garmin calls and then asked for a check that costs 5 on its own. That was
contradictory, and the agent running it correctly stopped rather than overspend —
which left the one check that actually mattered unrun. The budget below is
**~8 live calls**, which is what verifying the live path genuinely costs. Most
steps are free; the expensive ones are marked and justified.

---

```
Repo: SteinarR/garmin_mcp
Deploy: the TIP of branch claude/registry-ajlab-uk-refs-35pnyn
        (Deploy the tip, not a named commit. An earlier run pinned an
        intermediate commit and missed later fixes.)

GARMIN API BUDGET — READ FIRST
Garmin rate-limits the whole account to roughly 90-100 calls per day, shared
with the garmin-ingestor. This verification is budgeted at about 8 live calls.
That is deliberate and sufficient; do not exceed it.

  - Steps 1, 2, 3 and 6 cost ZERO live calls. Do those first.
  - Step 4 costs ~1. Step 5 costs ~5. Both are justified below.
  - Do NOT retry a failed call. Record the error and move on.
  - Do NOT call any range tool (get_trends, detect_anomalies,
    get_period_summary, get_optimized_health_data, get_coach_cues). They cost
    5-7 calls PER DAY of range.
  - Do NOT call get_sleep_data through MCP: ~280,000 characters, over the MCP
    result limit. It will fail and waste the call.
  - Prefer reading a file or a log over making a call, always.

Report your actual live-call count at the end.

WHAT CHANGED
Three related defects, all the same shape: code read a key that does not exist
in the payload Garmin actually returns, so a value silently became null while
looking correct against cached data.

  1. HRV. Live Garmin nests overnight HRV at hrvSummary.lastNightAvg; the code
     read the flat avgHrv/average keys that only the ingested-data cache
     produces. Affected get_readiness_breakdown, get_trends, detect_anomalies,
     get_data_completeness, get_period_summary.
  2. HRV scoring. A fixed 20-100 ms scale rated a 36 ms night 20/100 while
     Garmin itself called it BALANCED / 96 GOOD. Now scored against the user's
     own baseline, or Garmin's own hrvFactorPercent when available.
  3. Body battery. get_body_battery returns one object PER DAY with readings in
     bodyBatteryValuesArray; the code read bodyBatteryValue off the top-level
     rows. Affected the same tools plus get_coach_cues and
     get_training_and_diet_recommendations. Found by the previous verification
     run, via the new components_missing field.

Plus: the cache now warns when a read-only mount disables it, and the minimum
Python is 3.12 (the runtime is already 3.12.13, so this is metadata catching up
with reality — not a version change to the deployment).

STEP 1 — DEPLOY (0 calls)
Deploy the branch tip. Confirm the running container's commit before
continuing, and report it. The build path is NOT docker.sh — that file was
deleted; it pointed at the wrong registry. Note that if deploy.sh uses rsync
without --delete, a stale docker.sh may still sit on the VPS; ignore it.

STEP 2 — CACHE MOUNT, FROM LOGS (0 calls)
Look for either line at startup:

  Garmin cache enabled (dir=..., db=..., tiers=..., min_age_days=...)
  [garmin-cache] WARNING: cannot open '<db>' ... directory is read-only

The WARNING means the context-DB directory is mounted read-only, activity range
caching is OFF, and every range query is burning the API budget. Fix: mount the
directory holding the context DB READ-WRITE. The connection itself stays
mode=ro, so the server still cannot write to it. GARMIN_CACHE_DIR stays :ro.

Absence of the warning at startup proves nothing — it only fires on the first
query that touches the DB. Step 3 triggers it.

STEP 3 — EXERCISE THE CACHE (0 calls, with a preflight)
The cache is fail-open: a DB error or a missing raw file falls back to live
Garmin. So this is only free if you check first. Preflight, on the server, with
no MCP involved:
  - pick a 2-day range at least a week old
  - confirm the SQLite rows exist for it AND that every referenced raw activity
    file is present on disk

Then call get_activities_by_date for exactly that range, and re-check the logs
for the WARNING line. If it appears now, the mount is wrong: fix and redeploy.

STEP 4 — get_hrv_data ON A SETTLED DATE (~1 call, likely 0)
Pick ONE settled date at least 3 days old. Use the SAME date for steps 4 and 5.

  get_hrv_data(<settled date>)

Expect a JSON string and no error. This closes an open TOOLS.md note about a
Pydantic "Input should be a valid string" error reported long ago. Code
inspection says it cannot happen anymore. One clean call settles it — do not
retry it even though the original report described the error as intermittent.

STEP 5 — READINESS, SETTLED THEN TODAY (~5 calls)
Read this before running: the settled-date call is NOT a test of the HRV fix.
On a cached date, HRV arrives as flat avgHrv — the exact key the OLD broken
code read successfully. A settled date passing proves only that nothing
regressed. The bug was live-path-only, so "today" is the real test.

  5a. get_readiness_breakdown(<same settled date>)   ~1 call
      (Most inputs come off disk; get_stress_data is never cached, so it makes
      the one live request.)
      Check:
        components.hrv_score          not null
        components.body_battery_score not null   <-- the new fix; was null here
                                                     in the previous run
        components_missing            should be empty, or explain what is in it
        hrv_scoring_method            expect population_scale_approximate on a
                                      cached date, since the cache stores no
                                      HRV baseline
        garmin_training_readiness     Garmin's own score, for comparison

  5b. get_readiness_breakdown("today")               ~5 calls
      THIS IS THE ONE THAT MATTERS. Today is never served from cache, so all
      five inputs are live: sleep, body battery, training readiness, HRV,
      stress. That is what the 5 calls buy, and it is the only way to exercise
      the path that was broken.
      Check:
        components.hrv_score          not null  <-- was null on EVERY live call
        components.body_battery_score not null
        hrv_scoring_method            expect garmin_hrv_factor or
                                      personal_baseline here, NOT
                                      population_scale_approximate. If it is
                                      the population scale, the live payload
                                      carries no baseline and no Garmin factor
                                      — report that, it is useful.
        hrv_ms                        not null
      If 5a passes and 5b fails, the live payload shape differs from what the
      fix expects. Capture the raw shape from the logs — do NOT make another
      call — and report the top-level keys.

STEP 6 — DOES raw/stats ALREADY CONTAIN STRESS? (0 calls)
get_stress_data is never cached, for any date, because the ingestor does not
collect it. It is why step 5a costs a live call at all. But the ingestor DOES
store the daily stats payload verbatim, and Garmin's daily summary usually
carries an average stress field. If it is there, a derived stress tier is
possible with no new ingestion and no extra API cost anywhere — which would
take a settled-date readiness call from 1 live call to 0.

Just read a file already on disk:

  python3 -c "import json; d=json.load(open('/data/garmin/raw/stats/<settled date>.json')); print(sorted(k for k in d if 'stress' in k.lower()))"

Report the exact key names found (expect something like averageStressLevel,
maxStressLevel, stressDuration), or an empty list. Also print the value of the
average field if present. Do NOT call get_stress_data to compare — that costs a
call and the comparison can wait.

REPORT BACK
  1. Commit deployed (and confirm it is the branch tip).
  2. WARNING line present or absent, before and after step 3.
  3. Step 4: clean or not. Either way the TOOLS.md note can be closed.
  4. Steps 5a and 5b: hrv_score, body_battery_score, hrv_ms,
     hrv_scoring_method, components_used, components_missing,
     garmin_training_readiness.
  5. Step 6: the stress-related keys found in raw/stats, and the average value.
  6. Your actual live Garmin call count.
```

---

## Why the budget is 8 and not 3

There is no cheap way to test the live path. One `get_readiness_breakdown` on an
uncached date fans out to five client calls — sleep, body battery, training
readiness, HRV, stress — and the cache deliberately bypasses the first four for
recent dates because Garmin keeps revising them. Stress is never cached at all.

The previous run stayed inside a 3-call budget and passed every check it ran,
but every one of those checks hit the cache, where the bug never showed. The
settled-date result (`hrv_scoring_method: population_scale_approximate`, source
`garmin-ingestor-cache`) would have looked identical before the fix.

## What the previous run got right

Two prompt errors it correctly caught, both fixed above:

- **Step 3 is not unconditionally free.** The cache falls back to live Garmin on
  a DB error or a missing raw file. It now carries an explicit preflight.
- **Pin the tip, not a commit.** The previous run deployed the last code commit
  and missed a later one.

It also found the body battery bug, which no test caught because the test
fixture had been written from the consuming code rather than from a real
payload.
