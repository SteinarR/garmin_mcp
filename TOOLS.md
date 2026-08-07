# Garmin MCP Server - Available Tools

This document lists all MCP tools available in the Garmin MCP Server.

Registered is not the same as working. Read
[Known-broken tools](#known-broken-tools) before depending on anything below.
Five fail outright, one returns a payload too large to consume, and one returns
a wrong number without erroring.

## Core Activity Tools (from __init__.py)
- `list_activities(limit: int = 5)` - List recent Garmin activities

## Activity Management (9 tools)
- `get_activities_by_date(start_date: str, end_date: str, activity_type: str = "")` - Get activities between dates, optionally filtered by type
- `get_activities_fordate(date: str)` - Get activities for a specific date
- `get_activity(activity_id: int)` - Get basic activity information
- `get_activity_splits(activity_id: int)` - Get splits for an activity
- `get_activity_typed_splits(activity_id: int)` - Get typed splits for an activity
- `get_activity_split_summaries(activity_id: int)` - Get split summaries for an activity
- `get_activity_weather(activity_id: int)` - Get weather data for an activity
- `get_activity_hr_in_timezones(activity_id: int)` - Get heart rate data in different time zones
- `get_activity_gear(activity_id: int)` - Get gear data used for an activity
- `get_activity_exercise_sets(activity_id: int)` - Get exercise sets for strength training activities

## Health & Wellness (20 tools)
- `get_stats(date: str)` - Get daily activity stats
- `get_user_summary(date: str)` - Get user summary data (compatible with garminconnect-ha)
- `get_body_composition(start_date: str, end_date: str = None)` - Get body composition data
- `get_stats_and_body(date: str)` - Get stats and body composition data
- `get_steps_data(date: str)` - Get steps data
- `get_daily_steps(start_date: str, end_date: str)` - Get steps data for a date range
- `get_training_readiness(date: str)` - Get training readiness data
- `get_body_battery(start_date: str, end_date: str)` - Get body battery data
- `get_body_battery_events(date: str)` - Get body battery events data
- `get_blood_pressure(start_date: str, end_date: str)` - Get blood pressure data
- `get_floors(date: str)` - Get floors climbed data
- `get_training_status(date: str)` - Get training status data
- `get_rhr_day(date: str)` - Get resting heart rate data
- `get_heart_rates(date: str)` - Get heart rate data
- `get_hydration_data(date: str)` - Get hydration data
- `get_sleep_data(date: str)` - Get sleep data
- `get_stress_data(date: str)` - Get stress data
- `get_respiration_data(date: str)` - Get respiration data
- `get_spo2_data(date: str)` - Get SpO2 (blood oxygen) data
- `get_all_day_stress(date: str)` - Get all-day stress data
- `get_all_day_events(date: str)` - Get daily wellness events data

## User Profile (4 tools)
- `get_full_name()` - Get user's full name from profile
- `get_unit_system()` - Get user's preferred unit system
- `get_user_profile()` - Get user profile information
- `get_userprofile_settings()` - Get user profile settings

## Devices (6 tools)
- `get_devices()` - Get all Garmin devices associated with the user account
- `get_device_last_used()` - Get information about the last used Garmin device
- `get_device_settings(device_id: str)` - Get settings for a specific Garmin device
- `get_primary_training_device()` - Get information about the primary training device
- `get_device_solar_data(device_id: str, date: str)` - Get solar data for a specific device
- `get_device_alarms()` - Get alarms from all Garmin devices

## Gear Management (3 tools)
- `get_gear(user_profile_id: str)` - Get all gear registered with the user account
- `get_gear_defaults(user_profile_id: str)` - Get default gear settings
- `get_gear_stats(gear_uuid: str)` - Get statistics for specific gear

## Weight Management (5 tools)
- `get_weigh_ins(start_date: str, end_date: str)` - Get weight measurements between dates
- `get_daily_weigh_ins(date: str)` - Get weight measurements for a specific date
- `delete_weigh_ins(date: str, delete_all: bool = True)` - Delete weight measurements for a date
- `add_weigh_in(weight: float, unit_key: str = "kg")` - Add a new weight measurement
- `add_weigh_in_with_timestamps(weight: float, unit_key: str = "kg", date_timestamp: str = None, gmt_timestamp: str = None)` - Add weight measurement with specific timestamps

## Challenges & Badges (8 tools)
- `get_goals(goal_type: str = "active")` - Get Garmin Connect goals (active, future, or past)
- `get_personal_record()` - Get personal records for user
- `get_earned_badges()` - Get earned badges for user
- `get_adhoc_challenges(start: int = 0, limit: int = 100)` - Get adhoc challenges data
- `get_available_badge_challenges(start: int = 1, limit: int = 100)` - Get available badge challenges data
- `get_badge_challenges(start: int = 1, limit: int = 100)` - Get badge challenges data
- `get_non_completed_badge_challenges(start: int = 1, limit: int = 100)` - Get non-completed badge challenges data
- `get_race_predictions()` - Get race predictions for user
- `get_inprogress_virtual_challenges(start_date: str, end_date: str)` - Get in-progress virtual challenges/expeditions between dates

## Training & Performance (8 tools)
- `get_progress_summary_between_dates(start_date: str, end_date: str, metric: str)` - Get progress summary for a metric between dates
- `get_hill_score(start_date: str, end_date: str)` - Get hill score data between dates
- `get_endurance_score(start_date: str, end_date: str)` - Get endurance score data between dates
- `get_training_effect(activity_id: int)` - Get training effect data for a specific activity
- `get_max_metrics(date: str)` - Get max metrics data (like VO2 Max and fitness age)
- `get_hrv_data(date: str)` - Get Heart Rate Variability (HRV) data
- `get_fitnessage_data(date: str)` - Get fitness age data
- `request_reload(date: str)` - Request reload of epoch data

## Workouts (5 tools)
- `get_workouts()` - Get all workouts
- `get_workout_by_id(workout_id: int)` - Get details for a specific workout
- `download_workout(workout_id: int)` - Download a workout as a FIT file
- `upload_workout(workout_json: str)` - Upload a workout from JSON data
- `upload_activity(file_path: str)` - Upload an activity from a file (placeholder - not fully implemented)

## Data Management (3 tools)
- `add_body_composition(date: str, weight: float, percent_fat: Optional[float] = None, ...)` - Add body composition data
- `set_blood_pressure(systolic: int, diastolic: int, pulse: int, notes: Optional[str] = None)` - Set blood pressure values
- `add_hydration_data(value_in_ml: int, cdate: str, timestamp: str)` - Add hydration data

## Women's Health (3 tools)
- `get_pregnancy_summary()` - Get pregnancy summary data
- `get_menstrual_data_for_date(date: str)` - Get menstrual data for a specific date
- `get_menstrual_calendar_data(start_date: str, end_date: str)` - Get menstrual calendar data between dates

## Recommendations (8 tools)
- `get_optimized_health_data(start_date: str, end_date: str, include_activities: bool = True, include_sleep: bool = True, include_stress: bool = True, include_body_battery: bool = True, include_training_readiness: bool = True, include_hrv: bool = False, activity_type: str = "")` - Optimized tool to fetch multiple health and training data points in one call, reducing the need for multiple individual tool calls
- `get_training_and_diet_recommendations(context: str, health_data_json: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, focus_area: Optional[str] = None)` - Generate personalized training and diet recommendations based on recent health and training data, with context-aware suggestions
- `get_period_summary(period: str, anchor_date: Optional[str] = None, include_activities: bool = True, include_sleep: bool = True, include_stress: bool = True, include_body_battery: bool = True, include_training_readiness: bool = True, include_hrv: bool = False, include_stats: bool = True, activity_type: str = "")` - Single-pane summary for daily/weekly/monthly with aggregates and per-day details (accepts anchor phrases like "last week", "this month")
- `get_trends(start_date: str, end_date: str, include: Optional[List[str]] = None)` - Trends with 7/28-day rolling averages and start→end deltas for selected metrics (start/end may be relative phrases such as "last 28 days")
- `detect_anomalies(start_date: str, end_date: str, rhr_bpm_increase: int = 5, hrv_ms_drop: int = 15, sleep_hours_min: float = 6.0, steps_drop_pct: float = 30.0)` - Heuristic anomaly detection for recovery red flags (range accepts relative phrases)
- `get_readiness_breakdown(date: str)` - Component scores (sleep, body battery, HRV, stress inverse), which components resolved, and a combined readiness score (0–100) for a date or relative phrase (e.g., "today", "last week"). Reports Garmin's own training readiness alongside the composite
- `get_data_completeness(start_date: str, end_date: str)` - Per-day completeness and overall score across key signals (sleep, steps, HR, HRV, body battery) with support for relative ranges
- `get_hydration_guidance(weight_kg: float, training_minutes: int = 0, temperature_c: Optional[float] = None)` - Daily hydration target (ml) with baseline, training increment, and heat multiplier
- `get_coach_cues(period: str, anchor_date: Optional[str] = None)` - Concise coach guidance for daily/weekly/monthly periods using high-signal metrics

## Total: 78 MCP Tools

**Note:** Date parameters should be in `YYYY-MM-DD` format. Some tools may require specific Garmin device features or subscription levels to return data.

## Known-broken tools

Recorded so nobody spends an afternoon on a server-side failure. These are
registered and callable, but fail consistently in normal use. **Do not debug
them without new information** — the failures are upstream of this repo.

| Tool | Failure | Where it lives |
|---|---|---|
| `get_trends` | Errors on every date range, short or long | `recommendations.py` |
| `get_endurance_score` | Approval/execution errors | `training.py:68` |
| `get_race_predictions` | Approval/execution errors | `challenges.py:133` |
| `get_fitnessage_data` | Execution errors | `training.py:129` |
| `get_personal_record` | Execution errors | `challenges.py:47` |

`get_endurance_score` and `get_race_predictions` return "approval" errors, which
is Garmin declining the request for this account rather than a bug in the call —
no amount of parameter fiddling changes it.

### `get_hrv_data` — needs re-verification, not debugging

Reported as an intermittent Pydantic validation error (`Input should be a valid
string`, receiving a dict), succeeding on retry. That symptom is exactly what
`_to_json_str` fixed in `6273370` (2026-07-29), which is an ancestor of every
currently deployed ref — so either the observation predates the deploy, or the
cause is something else.

Left in place because it has not been re-tested since. It is also not on the
critical path: HRV arrives inside `get_sleep_data`, which is where the sleep
analyst reads it. If someone does re-test, record the result here and delete
this note either way.

### `get_sleep_data` — succeeds, but the result cannot be consumed

Observed live:

```
Error: result (280,351 characters) exceeds maximum allowed tokens.
```

The Garmin call works. `health_wellness.py:281` returns the payload verbatim,
and that payload is mostly per-minute time series that no summary consumer
reads:

| Field | Entries | Share of payload |
|---|---:|---:|
| `wellnessEpochSPO2DataDTOList` | 433 | 34.6% |
| `sleepMovement` | 553 | 24.0% |
| respiration epochs | 217 | 5.1% |
| `sleepHeartRate` | 217 | 3.6% |
| `sleepStress` / `sleepBodyBattery` | 145 each | 4.8% |
| **`dailySleepDTO` — the actual summary** | — | **1.1%** |

So an MCP client asking about last night gets an error and a spilled temp file
instead of the 2.9 KB it wanted out of 250 KB. The cache does not help: it
stores and serves the payload unmodified.

This is why the sleep analyst reads raw payloads off disk rather than calling
the tool. Anything that must go through MCP needs either a summary tool that
returns Garmin's own `dailySleepDTO` scores and qualifiers, or an opt-in flag
that drops the epoch series.

### `get_readiness_breakdown` — fixed, but still a heuristic

Both defects recorded here are fixed. Covered by `tests/test_readiness.py`,
which runs offline.

**The HRV component was dead on live data.** The tool read
`hrv.get("avgHrv") or hrv.get("average")`, but live `get_hrv_data` nests the
value at `hrvSummary.lastNightAvg`. It resolved to `None`, so readiness silently
became a three-component average instead of four — and it only populated when
served from cache, because `cache.py:201` flattens HRV to `avgHrv`. The bug
therefore disappeared exactly when tested against settled dates and reappeared
on today. `_extract_hrv_value` now reads both shapes, preferring the live one.

**The scale was miscalibrated when it did work.** The old map ran 20 ms → 0 and
100 ms → 100, so a 36 ms night scored **20/100** while Garmin's own baseline
called it `BALANCED` and rated the HRV factor 96 `GOOD`. HRV is too individual
for fixed millisecond thresholds. Scoring now runs in descending order of
trustworthiness, reported per call in `hrv_scoring_method`:

| Method | Source | When |
|---|---|---|
| `garmin_hrv_factor` | `hrvFactorPercent` from `get_training_readiness` | Live, and Garmin supplies the factor |
| `personal_baseline` | `hrvSummary.baseline` — the user's own balanced band | Live, no factor available |
| `population_scale_approximate` | Fixed 20-70 ms map | Cached dates, which carry no baseline |

On the recorded 36 ms night that scored 20: it now scores 96 via Garmin's own
factor, or 60 against the personal baseline when the factor is absent.

**A dropped component is now named, not hidden.** `components_used` and
`components_missing` say which components entered the average, so a three-way
composite is no longer indistinguishable from a four-way one. Garmin's own score
is reported alongside as `garmin_training_readiness` — prefer it where present,
since it is Garmin's model rather than this equal-weighted heuristic.

**The same defect at four other call sites is also fixed.** All of them now go
through `_extract_hrv_value`:

| Tool | Was |
|---|---|
| `get_trends` | `hrv` `None` for every day in the series |
| `detect_anomalies` | `hrv_depressed` could never fire — a real 30 ms drop went unflagged |
| `get_data_completeness` | HRV always scored absent, deflating the completeness score |
| `get_period_summary` | `avg_hrv` omitted from aggregates entirely |

Note that an earlier revision of this file named `get_optimized_health_data` and
`get_coach_cues` among the affected tools. That was wrong:
`get_optimized_health_data` stores the HRV payload verbatim and never extracts a
scalar, and `get_coach_cues` does not read HRV at all. The four above are the
real set.

### Confirmed stable

Depend on these freely:

- `get_sleep_data` (single date)
- `get_optimized_health_data` (date ranges)
- `get_activities_by_date` / `get_activities_fordate`
- `get_activity_splits`
- `get_activity_hr_in_timezones`
- `get_weigh_ins`

### Long sessions

Many sequential calls in one session hit rate limiting or drop the MCP
connection outright. For any backfill, prefer monthly chunks via
`get_optimized_health_data` over per-day calls, and keep the call count per
session modest. See the cache notes in [README.md](README.md#ingested-data-cache)
for how much of this the ingested-data cache absorbs.

