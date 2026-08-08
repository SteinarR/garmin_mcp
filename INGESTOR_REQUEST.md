# Request for the personal-ai / garmin-ingestor agent

## Does it need server access, or only the repo?

**Repo only.** Everything asked for below is a change to how the ingestor
normalises and writes payloads it already fetches. No server access is needed
to make the change.

Server access is only useful for two optional things:

- **Confirming the current on-disk shape** before editing. Not required — the
  evidence below was gathered from the garmin_mcp side and is already
  conclusive about what is and isn't stored.
- **Backfill.** A normalisation change only affects payloads written *after* it
  ships. Historical days keep whatever was stored at the time, and re-fetching
  them would cost real Garmin API calls. See the backfill note at the end; the
  default recommendation is not to backfill.

So: hand this to an agent with the repo. Only involve one with server access if
you decide to backfill.

---

```
Repo: the personal-ai / garmin-ingestor project (the service that writes
/data/garmin/raw/** and the context_kernel.db SQLite index).

CONTEXT
A separate MCP server (SteinarR/garmin_mcp) reads your ingested output as a
read-through cache so it can answer questions without calling Garmin, which
rate-limits the shared account to roughly 90-100 calls/day. It mounts
/data/garmin read-only and reads the raw payloads you write.

That works well for the categories you store verbatim. It breaks down for the
ones you normalise, and this request is about one of those.

THE PROBLEM
For `daily_training_state`, the stored payload contains exactly six fields:

    acuteLoad, calendarDate, chronicLoad, loadRatio,
    trainingReadiness, trainingStatusCode

Garmin's training-readiness response contains considerably more, including
`hrvFactorPercent` — Garmin's own 0-100 assessment of the night's HRV against
that user's personal baseline.

That field is discarded during normalisation. The consequence downstream: for
any date served from your data, the consumer cannot use Garmin's HRV
assessment and has to approximate it. Measured on real data, Garmin's factor
rated a night 94/100 where the fallback approximation gave 40/100.

The same applies to HRV generally. There is no stored HRV endpoint response at
all, so the consumer reconstructs an HRV-shaped object out of the raw sleep
payload's `avgOvernightHrv`. That reconstruction has no `hrvSummary.baseline`,
which is why the personal baseline is unavailable for historical dates.

WHAT I AM ASKING FOR — in preference order

1. STORE `daily_training_state` VERBATIM, the way you already store sleep,
   stats and body_battery.

   You already make the API call. The full response is already in memory. The
   only cost is disk, and these payloads are small — single-digit KB against
   the ~250KB sleep payloads you already retain for 730 days.

   This is preferred over "also keep hrvFactorPercent" because it fixes every
   future field nobody has thought to want yet, rather than just this one.

   If you need the normalised six-field form for your own queries, keep it —
   write both. The raw copy is additive.

2. IF VERBATIM IS NOT POSSIBLE, retain `hrvFactorPercent` alongside the
   existing six fields. Second-best, but it solves the immediate problem.

3. SEPARATELY, consider storing the HRV endpoint response
   (`get_hrv_data`) verbatim if you already call it. If you do NOT already
   call it, do not add the call — that spends Garmin budget, which defeats the
   purpose. Say so in your reply and stop at items 1-2.

CONSTRAINTS — please respect these
  - Do NOT add any new Garmin API request. Every item above is about what you
    do with responses you already have. If something appears to require a new
    call, do not make it: report that instead.
  - Do NOT change the existing six normalised fields, their names, or their
    units. A downstream consumer reads them today and will break.
  - Note that at least one category (`body_metrics`) is stored with converted
    units — weight in kg where Garmin returns grams — and the consumer
    converts back. If you write a verbatim copy anywhere, keep it genuinely
    verbatim: no unit conversion, no key renaming.

WHAT TO REPORT BACK
  1. Which option you implemented (1, 2, or neither) and why.
  2. The exact path and filename pattern of anything newly written, and
     whether it sits alongside or replaces the existing normalised record.
  3. Whether the existing six-field record is unchanged.
  4. Confirmation that no new Garmin API call was introduced.
  5. Whether you already fetch the HRV endpoint, and if so whether you now
     store it verbatim.
  6. When the change takes effect — specifically, that it applies only to
     payloads written from now on, and that historical days are unaffected.
```

---

## Evidence behind the request

Gathered from the consuming side, so it's independent of what the ingestor repo
claims about itself.

**The six-field payload**, read directly off the server from
`/data/garmin/raw/daily_training_state/2026-08-03.json`:

```
['acuteLoad', 'calendarDate', 'chronicLoad', 'loadRatio',
 'trainingReadiness', 'trainingStatusCode']
```

That is not a Garmin API response shape.

**Units are converted for at least one category.** `garmin_mcp/cache.py`
documents having to convert `body_metrics` weight back from kg to grams,
because the ingestor converted it on the way in. A verbatim copy cannot have
that done to it — which is how we know these records are normalised, not raw,
despite living under a directory called `raw/`.

**Four categories are already verbatim** — sleep, stats, body_battery,
activities. So the pattern being requested already exists in the codebase; this
is asking for one more category to follow it.

**The measured cost**, from a live verification run on 2026-08-07:

| Date | Source | HRV | Method | Score |
|---|---|---|---|---|
| today | live Garmin | 40 ms | Garmin's own `hrvFactorPercent` | **94** |
| settled | ingestor cache | 40 ms | fixed population scale | **40** |

## Backfill note

A normalisation change is not retroactive. Days already written keep their
six-field form, and re-fetching them would cost one Garmin call per day against
a ~90-100/day budget — 730 days of retention would take weeks of budget to
refill.

**Recommendation: do not backfill.** The consuming side has a mitigation that
needs no new data: it now derives a personal HRV baseline from percentiles over
the stored `avgOvernightHrv` history, which scores that same 40 ms night at 91
against Garmin's 94. That covers historical dates well enough, and new dates
pick up the real factor automatically once the ingestor change ships.

If you do want a backfill anyway, it should be a deliberate, rate-limited
background job with an explicit daily cap — not part of this change.
