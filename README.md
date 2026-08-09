# Garmin MCP Server

This Model Context Protocol (MCP) server connects to Garmin Connect and exposes your fitness and health data to OpenWebUI, Claude or any other MCP-compatible clients via Streamable HTTP transport.

Credits: https://github.com/Taxuspt/garmin_mcp

## Features

- **78+ MCP Tools** covering:
  - Activity management (list, get details, splits, weather, gear)
  - Health & wellness metrics (steps, heart rate, sleep, stress, body battery)
  - Training & performance data (VO2 Max, HRV, training effect, fitness age)
  - Device management
  - Gear tracking
  - Weight management
  - Challenges & badges
  - Workouts
  - Women's health data
  - Data management (add body composition, blood pressure, hydration)
  - Personalised training and diet recommedations

- **Streamable HTTP Transport** - Network-accessible MCP server for Kubernetes/container deployments
- **Token Persistence** - OAuth tokens cached to avoid repeated MFA prompts
- **Non-interactive MFA** - Supports containerised deployments with environment-based MFA codes

## Prerequisites

- Python 3.12+ (the container image and the deployed runtime are 3.12)
- Garmin Connect account credentials
- For Kubernetes: kubectl access to your cluster

## Deployment Options

### 1. Standalone (Local Development)

#### Installation

```bash
# Clone the repository
git clone <repository-url>
cd garmin_mcp

# Install dependencies
uv sync
```

#### Running

**With stdio transport (for MCP clients like Claude Desktop):**

```bash
export GARMIN_EMAIL="your-email@example.com"
export GARMIN_PASSWORD="your-password"
export GARMIN_MCP_TRANSPORT="stdio"

uv run garmin-mcp
```

**With Streamable HTTP transport (for network access):**

```bash
export GARMIN_EMAIL="your-email@example.com"
export GARMIN_PASSWORD="your-password"
export GARMIN_MCP_TRANSPORT="streamable-http"
export GARMIN_MCP_HOST="0.0.0.0"
export GARMIN_MCP_PORT="8000"

uv run garmin-mcp
```

The server will be accessible at `http://localhost:8000/mcp`

#### First-Time Setup (MFA - Only if enabled on Garmin Connect)

If you have MFA enabled on your Garmin Connect account, you'll need to provide the 2FA code on first run. You have two options:

**Option A: Interactive (for local development)**
- The server will prompt for the MFA code in the terminal

**Option B: Non-interactive (for automation)**
```bash
export GARMIN_MFA_CODE="123456"  # Code from email/SMS
export GARMIN_MFA_WAIT_SECONDS="180"  # Optional: wait up to 180s for code to appear
```

**Note:** If MFA is not enabled on your Garmin Connect account, you can skip these environment variables.

After successful login, OAuth tokens are saved to `~/.garminconnect` and future runs won't require MFA until tokens expire.

#### Configuration with Claude Desktop

Edit your Claude Desktop configuration:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uv",
      "args": ["run", "garmin-mcp"],
      "env": {
        "GARMIN_EMAIL": "your-email@example.com",
        "GARMIN_PASSWORD": "your-password",
        "GARMIN_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

**Note:** If you have MFA enabled on your Garmin Connect account, add `"GARMIN_MFA_CODE": "123456"` to the `env` section for the first run.

Restart Claude Desktop after making changes.

### 2. Docker Deployment

#### Build the Image

```bash
docker build -t garmin-mcp:latest .
```

#### Run the Container

**Basic run (stdio transport):**

```bash
docker run --rm -it \
  -e GARMIN_EMAIL="your-email@example.com" \
  -e GARMIN_PASSWORD="your-password" \
  -e GARMIN_MCP_TRANSPORT="stdio" \
  -v garmin_tokens:/root/.garminconnect \
  garmin-mcp:latest
```

**Network-accessible (Streamable HTTP):**

```bash
docker run --rm -it \
  -e GARMIN_EMAIL="your-email@example.com" \
  -e GARMIN_PASSWORD="your-password" \
  -e GARMIN_MCP_TRANSPORT="streamable-http" \
  -e GARMIN_MCP_HOST="0.0.0.0" \
  -e GARMIN_MCP_PORT="8000" \
  -e GARMIN_MFA_CODE="123456" \
  -e GARMIN_MFA_WAIT_SECONDS="180" \
  -p 8000:8000 \
  -v garmin_tokens:/root/.garminconnect \
  garmin-mcp:latest
```

**Note:** Only include `GARMIN_MFA_CODE` and `GARMIN_MFA_WAIT_SECONDS` if you have MFA enabled on your Garmin Connect account.

The server will be accessible at `http://localhost:8000/mcp`

**Using Docker Compose:**

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  garmin-mcp:
    build: .
    image: garmin-mcp:latest
    container_name: garmin-mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - GARMIN_EMAIL=${GARMIN_EMAIL}
      - GARMIN_PASSWORD=${GARMIN_PASSWORD}
      - GARMIN_MCP_TRANSPORT=streamable-http
      - GARMIN_MCP_HOST=0.0.0.0
      - GARMIN_MCP_PORT=8000
      # Only include MFA variables if MFA is enabled on your Garmin Connect account
      - GARMIN_MFA_CODE=${GARMIN_MFA_CODE}
      - GARMIN_MFA_WAIT_SECONDS=180
    volumes:
      - garmin_tokens:/root/.garminconnect

volumes:
  garmin_tokens:
```

Run with:

```bash
docker-compose up -d
```

### 3. Kubernetes Deployment

#### Prerequisites

- Kubernetes cluster with kubectl configured
- PersistentVolume support (for token storage)

#### Step 1: Create Secrets

Create a Kubernetes Secret with your Garmin credentials:

```bash
kubectl create namespace mcpo  # or your preferred namespace

kubectl create secret generic garmin-secrets \
  --from-literal=email='your-email@example.com' \
  --from-literal=password='your-password' \
  --from-literal=mfa='123456' \
  -n mcpo
```

**Note:** The `mfa` key is only needed if you have MFA enabled on your Garmin Connect account. If MFA is not enabled, omit the `--from-literal=mfa` line. The `mfa` key is only needed for the first run or when tokens expire. You can remove it after tokens are established.

#### Step 2: Create PersistentVolumeClaim

Create `pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: garmin-tokens
  namespace: mcpo
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

Apply it:

```bash
kubectl apply -f pvc.yaml
```

#### Step 3: Deploy the Application

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: garmin-mcp
  namespace: mcpo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: garmin-mcp
  template:
    metadata:
      labels:
        app: garmin-mcp
    spec:
      containers:
        - name: garmin-mcp
          image: garmin-mcp:latest  # Replace with your image registry
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              name: http
          env:
            - name: GARMIN_EMAIL
              valueFrom:
                secretKeyRef:
                  name: garmin-secrets
                  key: email
            - name: GARMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: garmin-secrets
                  key: password
            - name: GARMIN_MCP_TRANSPORT
              value: "streamable-http"
            - name: GARMIN_MCP_HOST
              value: "0.0.0.0"
            - name: GARMIN_MCP_PORT
              value: "8000"
            # Only include MFA variables if MFA is enabled on your Garmin Connect account
            - name: GARMIN_MFA_CODE
              valueFrom:
                secretKeyRef:
                  name: garmin-secrets
                  key: mfa
            - name: GARMIN_MFA_WAIT_SECONDS
              value: "180"
          volumeMounts:
            - name: tokens
              mountPath: /root/.garminconnect
          readinessProbe:
            tcpSocket:
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            tcpSocket:
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
      volumes:
        - name: tokens
          persistentVolumeClaim:
            claimName: garmin-tokens
```

Apply it:

```bash
kubectl apply -f deployment.yaml
```

#### Step 4: Create Service

Create `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: garmin-mcp
  namespace: mcpo
spec:
  selector:
    app: garmin-mcp
  ports:
    - name: http
      port: 80
      targetPort: 8000
  type: ClusterIP
```

Apply it:

```bash
kubectl apply -f service.yaml
```

#### Step 5: (Optional) Create Istio HTTPRoute

If using Istio, create `httproute.yaml`:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: garmin-mcp
  namespace: mcpo
spec:
  parentRefs:
    - name: your-gateway
      namespace: istio-system
  hostnames:
    - garmin-mcp.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /mcp
      backendRefs:
        - name: garmin-mcp
          port: 80
```

Apply it:

```bash
kubectl apply -f httproute.yaml
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GARMIN_EMAIL` | Garmin Connect email address | - | Yes |
| `GARMIN_PASSWORD` | Garmin Connect password | - | Yes |
| `GARMIN_MFA_CODE` | 2FA code (only if MFA is enabled) | - | No* |
| `GARMIN_MFA_WAIT_SECONDS` | Seconds to wait for MFA code | `0` | No |
| `GARMINTOKENS` | Path to token storage directory | `~/.garminconnect` | No |
| `GARMIN_MCP_TRANSPORT` | Transport type: `stdio` or `streamable-http` | `http` | No |
| `GARMIN_MCP_HOST` | Bind host for HTTP transport | `0.0.0.0` | No |
| `GARMIN_MCP_PORT` | Port for HTTP transport | `8000` | No |
| `GARMIN_CACHE_ENABLED` | Serve settled reads from ingested data | `false` | No |
| `GARMIN_CACHE_DIR` | garmin-ingestor data directory | `/data/garmin` | No |
| `GARMIN_CACHE_DB` | Context SQLite DB (needed for activity ranges) | - | No |
| `GARMIN_CACHE_MIN_AGE_DAYS` | Freshness floor; newer dates always go live | `1` | No |
| `GARMIN_CACHE_DERIVED` | Also serve lossy derived payloads | `false` | No |
| `GARMIN_CACHE_VERBOSE` | Log every cache decision | `false` | No |

*Required only if MFA is enabled on your Garmin Connect account, and only on first run or when tokens expire

## API Budget

**Garmin rate-limits hard, and the budget is the binding constraint on this
server. Make only the calls you actually need.**

Garmin Connect tolerates roughly **90-100 API calls per day** across the whole
account. Exceeding it does not fail cleanly — calls start erroring, and long
sessions drop the MCP connection outright. The budget is shared with anything
else touching the same account, including the ingestor.

Practical rules:

- **Never call a range tool to get one day.** The per-day loops cost 5-7 calls
  for *every* day in the range, cached or not.
- **Prefer `get_optimized_health_data` over per-day calls** for any backfill,
  and take it in monthly chunks rather than one long span.
- **Ask for the metrics you need**, not the defaults. `get_trends` and
  `get_period_summary` both take include-lists; every extra metric is another
  call per day.
- **Settled dates are nearly free** where the cache covers them; today and
  yesterday are never cached and always cost live calls. See
  [Freshness](#freshness).
- **Watch for `[garmin-cache] WARNING`** in the logs. It means the cache is off
  and every query is hitting Garmin.
- **Keep sessions short.** Many sequential calls in one session hit rate
  limiting or drop the connection.

## Ingested Data Cache

Tools that loop over a date range (`detect_anomalies`,
`get_optimized_health_data`, `get_period_summary`, `get_coach_cues`) spend 5-7
calls *per day of range*, so a 90-day query alone can exhaust the daily budget
several times over.

If this server runs alongside a
[garmin-ingestor](https://github.com/steinarr/personal-ai) deployment, it can
read that data instead of calling Garmin. The ingestor already persists raw
payloads (730-day retention) and a SQLite index on a 6-hourly cron.

Enable it by mounting the ingestor's volumes read-only and setting:

```bash
GARMIN_CACHE_ENABLED=true
GARMIN_CACHE_DIR=/data/garmin
GARMIN_CACHE_DB=/context-db/context_kernel.db
GARMIN_CACHE_DERIVED=true
```

```yaml
volumes:
  - /srv/dev/garmin:/data/garmin:ro
  # Not :ro — see below.
  - /var/lib/personal-ai/dev:/context-db
```

The context DB directory must be mounted **read-write** even though this server
only ever reads it. The ingestor runs SQLite in WAL mode, and opening a WAL
database requires a `-shm` file alongside it; if that file has to be created and
the mount is read-only, the open fails and activity range caching silently
degrades to live API calls. The connection itself is opened with `mode=ro`, so
this server still cannot write to the database. The data directory is genuinely
read-only and should stay `:ro`.

A read-only mount may appear to work when tested, which makes this easy to get
wrong. SQLite keeps `-wal` and `-shm` on disk only while at least one connection
is open, and deletes them when the last one closes. On the current server a
long-running API container holds a connection permanently, so the files are
always present and a read-only mount can reuse them. Stop that container while
nothing else is connected and the files disappear — after which a read-only
mount cannot recreate them. Testing the mount proves nothing about the state you
will eventually be in.

This no longer fails silently. When SQLite reports `SQLITE_READONLY_DIRECTORY`,
the server logs once, regardless of `GARMIN_CACHE_VERBOSE`:

```
[garmin-cache] WARNING: cannot open '/context-db/context_kernel.db' because its
directory is read-only. ... Activity range caching is OFF and every range query
is going to the live Garmin API instead.
```

Seeing that line means the mount is wrong and you are burning the API budget.
Any other SQLite failure warns once too, with the underlying error.

The cache is **read-through and fail-open**: a miss, an unrecognized argument
shape, or any cache error falls back to the live API. It is disabled unless
`GARMIN_CACHE_ENABLED` is set, so existing deployments are unaffected.

### Fidelity tiers

**Exact** (`GARMIN_CACHE_ENABLED`) — the stored payload is byte-identical to what
Garmin returned, so tools cannot tell the difference:

| Call | Source |
|------|--------|
| `get_sleep_data(date)` | `raw/sleep/{date}.json` |
| `get_stats(date)` | `raw/stats/{date}.json` |
| `get_body_battery(date, date)` | `raw/body_battery/{date}.json` |
| `get_activities_by_date(start, end)` | SQLite `start_time` index + `raw/activities/{id}.json` |
| `get_training_readiness(date)` | `raw/daily_training_state/{date}.json` → `trainingReadinessRaw` |
| `get_training_status(date)` | `raw/daily_training_state/{date}.json` → `trainingStatusRaw` |

`get_stats` and `get_body_battery` require the ingestor's `daily_wellness`
category (`GARMIN_ENABLE_DAILY_WELLNESS=true`), which is off by default there.
Only the single-day `get_body_battery` form is cached; wider ranges stay live.

The two training-state calls are exact **only for days whose stored payload
carries `trainingReadinessRaw` / `trainingStatusRaw`**. The ingestor used to
keep just six normalized fields and discard the rest, which cost
`hrvFactorPercent` among others; it now attaches the untouched source responses
alongside them.

Live since 2026-08-08, covering 2026-08-01 onward. The ingestor re-fetches a
rolling window rather than only the current day, so its first run after
deployment wrote the blocks for eight days at once — six of which were already
past the 2-day training-state freshness floor, making the change usable the same
evening. Check coverage at any time with:

```bash
grep -l trainingReadinessRaw /data/garmin/raw/daily_training_state/*.json | head
```

Days older than that first window keep the six-field record. They are not
backfilled — re-fetching 730 days would cost one Garmin call each — so the
derived form stays regardless.

The tier is therefore decided per day, by what is actually on disk, not per
method: a stored verbatim payload is exact and served regardless of
`GARMIN_CACHE_DERIVED`, while the normalized reconstruction honours that flag
like everything else in the derived tier.

**Derived** (`GARMIN_CACHE_DERIVED`) — the ingestor normalizes these, so the
response carries only the retained fields and is tagged `"_partial": true`:

| Call | Source | Retained |
|------|--------|----------|
| `get_rhr_day(date)` | raw sleep | `restingHeartRate` |
| `get_hrv_data(date)` | raw sleep | `avgOvernightHrv`, `hrvStatus`, `hrvData` |
| `get_training_readiness(date)` | `raw/daily_training_state/` | readiness score — days without a raw block, see above |
| `get_training_status(date)` | `raw/daily_training_state/` | status code, acute/chronic load — days without a raw block |
| `get_body_composition(date)` | `raw/body_metrics/` | weight, muscle mass, body fat |

Everything else — `get_stress_data`, `get_max_metrics`, `get_heart_rates`,
`get_activities`, and every write method — passes straight through to the live
client.

With both tiers enabled and the ingestor's `daily_wellness` category on, a
`get_trends` call over its default metric set (`rhr`, `hrv`, `sleep`, `steps`,
`body_battery`) is served entirely from disk for settled dates, down from 5
Garmin calls per day of range to zero.

### Known coverage limits

Raw retention on the ingestor was originally 30 days and was later raised to
730. Payloads deleted under the old policy are gone from disk.

As of 2026-07-29 this affects activities: 69 of 98 indexed activities have no
raw file, so `get_activities_by_date` falls back to the live API for any range
that includes them. The cost is low — that call fetches a whole range in one
request, unlike the per-day endpoints where each missing date costs its own
call. Sleep has no gaps.

Three calls in the per-day loops are still uncached: `get_stress_data`,
`get_max_metrics` and `get_heart_rates`. Two of them are genuinely uncollected,
and covering those would need another ingestion category on the personal-ai
side, at further API-call cost there.

**`get_stress_data` is the exception, and it is cheap to fix.** The data is
already on disk. `raw/stats/{date}.json` is stored verbatim and carries
eighteen stress fields, including the one thing readiness actually reads:

```
averageStressLevel   maxStressLevel      stressQualifier
stressDuration       restStressDuration  lowStressDuration
highStressDuration   mediumStressDuration              (and ten more)
```

Confirmed on the server 2026-08-07: `averageStressLevel = 23` for a settled
date. A derived `get_stress_data` mapped from the stored stats payload needs no
new ingestion category and no additional API call anywhere. It would take a
settled-date `get_readiness_breakdown` from one live Garmin request to zero,
since stress is currently the only input to that tool the cache cannot serve.

`get_activities` (most-recent-N) is deliberately never cached. It exists to
return the newest activities, which is exactly the data a periodically-synced
cache cannot be trusted for.

### Reading the verbose log

`GARMIN_CACHE_VERBOSE=true` emits one `[garmin-cache]` line for every decision,
so a call that reaches the cache never passes without a trace:

| Line | Meaning |
|------|---------|
| `hit` | Served from disk. No Garmin call. |
| `miss` | Old enough to serve, but no stored payload. Fell back to the API. |
| `skip` | Newer than the freshness floor, so the API was used deliberately. **Not a fault.** |
| `bypass` | Argument shape the cache does not handle (a date range, an unparseable date). |

A run with only `skip` lines is a cache working as designed against recent
dates, not a broken one — to see hits, request a date older than
`GARMIN_CACHE_MIN_AGE_DAYS` (or older than 2 days for training status and
readiness, which use a stricter floor).

Leave this off in normal operation. It is per-call, and container logs are
usually size-capped.

### Unbounded date ranges

Independent of the cache: the range tools in `recommendations.py` —
`get_trends`, `detect_anomalies`, `get_optimized_health_data`,
`get_period_summary`, `get_coach_cues` — accept an arbitrary date range and loop
day by day with no upper limit. Every uncached metric costs one API call per day
of range, so a single 365-day request can issue well over a thousand calls
against a ~90-100/day budget.

(`get_trends` is in that list for completeness only — it errors on every range
it is given, so it never reaches the loop. See
[Known-broken tools](TOOLS.md#known-broken-tools).)

The cache reduces this sharply where it has coverage, but it is not a limit. A
sanity cap on range length would be worth adding on its own merits.

### Freshness

Dates newer than `GARMIN_CACHE_MIN_AGE_DAYS` always go to the live API, because
the ingestor runs on a 6-hourly cron and Garmin keeps revising recent days.
Training status and readiness use a stricter 2-day floor to match the ingestor's
own recompute window. `get_activities_by_date` is only served from cache when the
*entire* range is settled, so a partially-ingested window can never silently drop
an activity.

## Token Management

OAuth tokens are automatically saved to `~/.garminconnect` (or path specified by `GARMINTOKENS`) after successful login. These tokens persist across restarts, eliminating the need for MFA on subsequent runs until they expire.

**For Kubernetes:** Tokens are stored in the PersistentVolumeClaim, so they persist across pod restarts and deployments.

## Troubleshooting

### Login Issues

1. **Invalid credentials**: Verify your email and password are correct
2. **MFA required**: If you have MFA enabled, ensure `GARMIN_MFA_CODE` is set for first run
3. **Token expired**: Delete the token directory and re-authenticate

### Network Issues

1. **Can't connect to server**: Verify the server is binding to `0.0.0.0` (not `127.0.0.1`)
2. **Connection refused**: Check firewall rules and port exposure
3. **404 errors**: Ensure you're using the correct transport type (Streamable HTTP for network access)

### Tools that fail, and tools that lie

Three separate failure modes, all catalogued in
[TOOLS.md](TOOLS.md#known-broken-tools). Check there before spending time on a
call that misbehaves.

**Fails outright, upstream of this repo — do not debug.** `get_trends`,
`get_endurance_score`, `get_race_predictions`, `get_fitnessage_data`,
`get_personal_record`. A sixth, `get_hrv_data`, has an older report that may
already be fixed and needs re-verification rather than debugging.

**Succeeds but cannot be consumed.** `get_sleep_data` returns ~280,000
characters, which exceeds the MCP result limit. Two-thirds of that is per-minute
time series; the summary a caller actually wants is about 1% of the payload.

**Succeeded and returned a wrong answer — now fixed.**
`get_readiness_breakdown` read HRV from a field live Garmin does not populate,
so the component silently dropped out, and the 20–100 ms scale rated a normal
night at 20/100. It now reads both the live and cached HRV shapes and scores
against the user's own Garmin baseline, naming the components that actually
entered the average. The same flat-key read silently blanked HRV in `get_trends`,
`detect_anomalies`, `get_data_completeness` and `get_period_summary` too, and is
fixed there as well; see [TOOLS.md](TOOLS.md#known-broken-tools).

### Kubernetes Issues

1. **Pod crash loops**: Check logs with `kubectl logs -n mcpo deployment/garmin-mcp`
2. **Service not accessible**: Verify Service selector matches Deployment labels
3. **Token persistence**: Ensure PVC is properly mounted and has storage available

### Viewing Logs

**Docker:**
```bash
docker logs <container-id>
```

**Kubernetes:**
```bash
kubectl logs -n mcpo deployment/garmin-mcp -f
```

## Available Tools

This server provides 78+ MCP tools. See [TOOLS.md](TOOLS.md) for a complete list organised by category.

## Example Queries

Once connected to the MCP server, you can query your Garmin fitness data using natural language. Here are some example queries you can make:

### Activity Queries

- **"Show me my recent activities"**
  - Uses: `list_activities`
  
- **"What running activities did I do between September 1st and November 6th?"**
  - Uses: `get_activities_by_date` with activity_type="running"
  
- **"Get details for activity ID 204592654"**
  - Uses: `get_activity`
  
- **"Show me the splits for my last run"**
  - Uses: `get_activity_splits`
  
- **"What was the weather during my activity 204592654?"**
  - Uses: `get_activity_weather`

### Health & Wellness Queries

- **"How many steps did I take on November 6th?"**
  - Uses: `get_steps_data`
  
- **"Show me my sleep data for November 5th"**
  - Uses: `get_sleep_data`
  
- **"What was my heart rate on November 6th?"**
  - Uses: `get_heart_rates`
  
- **"Get my body battery data from November 1st to November 6th"**
  - Uses: `get_body_battery`
  
- **"What was my stress level on November 5th?"**
  - Uses: `get_stress_data` or `get_all_day_stress`
  
- **"Show me my resting heart rate for November 6th"**
  - Uses: `get_rhr_day`
  
- **"Get my body composition data for November 6th"**
  - Uses: `get_body_composition`
  
- **"What was my training readiness on November 6th?"**
  - Uses: `get_training_readiness`
  
- **"Show me my hydration data for November 6th"**
  - Uses: `get_hydration_data`
  
- **"Get my SpO2 (blood oxygen) data for November 6th"**
  - Uses: `get_spo2_data`
  
- **"What was my respiration rate on November 6th?"**
  - Uses: `get_respiration_data`

### Training & Performance Queries

- **"What's my VO2 Max and fitness age for November 6th?"**
  - Uses: `get_max_metrics`
  
- **"Get my HRV (Heart Rate Variability) data for November 6th"**
  - Uses: `get_hrv_data`
  
- **"Show me my fitness age data for November 6th"**
  - Uses: `get_fitnessage_data`
  
- **"What was my training effect for activity 204592654?"**
  - Uses: `get_training_effect`
  
- **"Get my hill score from September 1st to November 6th"**
  - Uses: `get_hill_score`
  
- **"Show me my endurance score between September 1st and November 6th"**
  - Uses: `get_endurance_score`

### Device & Gear Queries

- **"List all my Garmin devices"**
  - Uses: `get_devices`
  
- **"What's my primary training device?"**
  - Uses: `get_primary_training_device`
  
- **"Show me the gear I used for activity 204592654"**
  - Uses: `get_activity_gear`

### Challenges & Goals Queries

- **"What are my active goals?"**
  - Uses: `get_goals` with goal_type="active"
  
- **"Show me my personal records"**
  - Uses: `get_personal_record`
  
- **"What badges have I earned?"**
  - Uses: `get_earned_badges`
  
- **"Get my race predictions"**
  - Uses: `get_race_predictions`

### User Profile Queries

- **"What's my full name?"**
  - Uses: `get_full_name`
  
- **"What unit system do I use?"**
  - Uses: `get_unit_system`
  
- **"Show me my user profile"**
  - Uses: `get_user_profile`

### Data Management Queries

- **"Add a weight measurement: 75.5 kg"**
  - Uses: `add_weigh_in`
  
- **"Get my weight measurements from November 1st to November 6th"**
  - Uses: `get_weigh_ins`
  
- **"Add body composition data for November 6th"**
  - Uses: `add_body_composition`

### Training and Diet Recommedations

- **"Prepare me for a marathon with training and diet recommendations"**
  - Uses: `get_training_and_diet_recommendations`
  
- **"I want to improve my running performance, give me training and diet recommendations"**
  - Uses: `get_training_and_diet_recommendations`
  
- **"I want to lose weight - what should I do?"**
  - Uses: `get_training_and_diet_recommendations`

### Complex Queries

The MCP server can handle complex, multi-step queries:

- **"Analyze my training week: show me my activities, sleep quality, and body battery from November 1st to November 6th"**
  - Combines: `get_activities_by_date`, `get_sleep_data`, `get_body_battery`
  
- **"Compare my running performance: get my activities, training effect, and heart rate zones for my last 5 runs"**
  - Combines: `list_activities`, `get_training_effect`, `get_activity_hr_in_timezones`
  
- **"Give me a complete health summary for November 6th: steps, sleep, stress, heart rate, and body battery"**
  - Combines: `get_steps_data`, `get_sleep_data`, `get_stress_data`, `get_heart_rates`, `get_body_battery`

### One‑Pane Summaries and Insights

- **"Show my weekly single-pane summary for last week"**
  - Uses: `get_period_summary` with period="weekly", anchor_date="last week"
  
- **"Fetch a monthly dashboard summary including activities and readiness"**
  - Uses: `get_period_summary` with period="monthly"
  
- **"What are my trends over the last 4 weeks?"**
  - Uses: `get_trends` with start_date, end_date, include=["rhr","hrv","sleep","steps","body_battery"]
  
- **"Detect any recovery red flags this week"**
  - Uses: `detect_anomalies` with heuristic thresholds (defaults sensible)
  
- **"Give me a readiness breakdown for today"**
  - Uses: `get_readiness_breakdown`
  
- **"How complete is my data this month?"**
  - Uses: `get_data_completeness`
  
- **"Hydration target for a 60‑minute run at 28°C, weight 75 kg"**
  - Uses: `get_hydration_guidance` with weight_kg=75, training_minutes=60, temperature_c=28
  
- **"Coach cues for this week"**
  - Uses: `get_coach_cues` with period="weekly"

> Tip: These tools accept natural timeframe phrases like `today`, `yesterday`, `last week`, `this week`, `last month`, `last 28 days`. Ranges automatically clamp to today so mid-week requests never reach into the future.

### Accessing the Server

When deployed with Streamable HTTP transport, the MCP server is accessible at:

- **Local**: `http://localhost:8000/mcp`
- **Kubernetes with Istio**: `https://garmin-mcp.example.com/mcp`
- **Docker**: `http://<container-ip>:8000/mcp`

Configure your MCP client (OpenWebUI, Claude, etc.) to connect to the `/mcp` endpoint for Streamable HTTP transport.

## Security Notes

- **Never commit credentials**: Use environment variables or Kubernetes Secrets
- **Token storage**: Tokens are stored locally/on PVC - ensure proper access controls
- **Network security**: For production, use TLS/HTTPS (terminate at Ingress/Gateway)
- **Secret rotation**: Rotate Garmin password regularly and update secrets accordingly

## Outstanding work

An index, not a spec — each item is described where it belongs, and this list
exists only because the backlog was otherwise scattered across two files. Keep
it short: delete an entry when it is done rather than marking it.

**Costs API budget until fixed**

- **Derive `get_stress_data` from the stored stats payload.** The data is
  already on disk; this needs no new ingestion and no extra API call. It is the
  only reason a settled-date `get_readiness_breakdown` still spends a live
  request. See [Known coverage limits](#known-coverage-limits).
- **Cap the unbounded date ranges.** The per-day loops accept any range and
  have no ceiling, so one 365-day call can issue over a thousand requests. See
  [Unbounded date ranges](#unbounded-date-ranges).

**Tools that do not work**

- **`get_sleep_data` cannot be consumed through MCP** — ~280,000 characters,
  over the result limit, of which the summary is about 1%. Needs a summary tool
  or a flag that drops the epoch series.
- **Five tools fail upstream of this repo** and are marked do-not-debug.
- **`upload_activity` is a stub** that returns "not supported" while `TOOLS.md`
  advertises it. Implement or remove.

All three are catalogued in [TOOLS.md](TOOLS.md#known-broken-tools).

**Infrastructure**

- **No CI.** There are 100+ offline tests and nothing runs them automatically.
  `pyproject.toml` already excludes the credential-requiring scripts, so a
  minimal `pytest` workflow is close to free. Note that one test skips as root.
- **Detect the read-only mount at startup**, rather than on the first query
  that touches the DB. The warning exists; it just fires late.

**Depends on the ingestor (personal-ai), not actionable here**

- `get_max_metrics` and `get_heart_rates` are genuinely uncollected and would
  need a new ingestion category, at API cost there.
- `daily_wellness` is off by default, which blocks exact-tier `get_stats` and
  `get_body_battery`.
- Only single-day `get_body_battery` is cached; wider ranges stay live.
- Days written before that ingestor change keep the six-field training-state
  record and are deliberately not backfilled.

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
