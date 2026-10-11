# Carbon Emissions Reporting Platform

A prototype platform for organizations to track, calculate, and report their Greenhouse Gas (GHG) emissions based on the **GHG Protocol**, with a focus on **Scope 1 (Direct)** and **Scope 2 (Indirect)** emissions, versioned emission-factor master data, an override audit trail, and an advanced analytics engine (YoY, emission intensity, hotspots, monthly trends).

Built for the **Data Developer Intern assignment — Exascale Deeptech & AI Pvt. Ltd.**

---

## 1. Architecture & Technology Stack

### 1.1 Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            Browser (single page)                           │
│  static/index.html + app.js + Chart.js (bundled locally, works offline)    │
│  • Dashboard: KPI cards, stacked YoY bar, hotspot donut, monthly line      │
│  • Forms: Scope 1/2 record submission, business metric submission          │
│  • Tables: recent records, override audit log                              │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │ fetch() JSON  (same origin, /api/*)
┌──────────────────────────────▼─────────────────────────────────────────────┐
│                      FastAPI application  (app/main.py)                    │
│                                                                            │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────────────┐  │
│  │ records.py    │  │ analytics.py  │  │ metrics.py                     │  │
│  │ POST records  │  │ GET yoy       │  │ GET/POST business-metrics      │  │
│  │ PATCH override│  │ GET intensity │  └────────────────────────────────┘  │
│  │ DELETE revert │  │ GET hotspot   │                                     │
│  │ GET audit-log │  │ GET monthly   │                                     │
│  │ GET factors   │  └───────┬───────┘                                     │
│  └───────┬───────┘          │                                             │
│  ┌───────▼──────────────────▼────────────┐                                │
│  │ engine.py — Calculation Engine        │                                │
│  │ resolve_factor(activity, date)        │  ← historical accuracy: picks  │
│  │ emissions = quantity × factor         │    the factor valid ON the     │
│  └──────────────────┬────────────────────┘    activity date, not the      │
│                     │ SQLAlchemy ORM (2.0)          latest version        │
└─────────────────────┼──────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────────────────┐
│                        SQLite database  (data/ghg_platform.db)             │
│  emission_factors (versioned) · emission_records · audit_log ·             │
│  business_metrics                                                          │
└────────────────────────────────────────────────────────────────────────────┘
                      ▲
┌─────────────────────┴──────────────────────────────────────────────────────┐
│  seed.py — one-time seeding from data/ghg_sheet.xlsx (GHG workbook)        │
│  Runs automatically on app startup if the DB is empty (idempotent).        │
└────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack & Rationale

| Layer     | Choice                          | Why |
|-----------|---------------------------------|-----|
| Backend   | **Python 3.12 + FastAPI**       | Fast, typed, auto-generated OpenAPI docs at `/docs`, minimal boilerplate for a prototype API. |
| ORM       | **SQLAlchemy 2.0**              | Mature ORM; declarative models map cleanly to the versioned master-data schema. |
| Database  | **SQLite**                      | Zero-configuration, file-based, perfect for a containerized prototype. The schema is standard SQL and ports to PostgreSQL unchanged. |
| Frontend  | **Vanilla JS + Chart.js 4**     | No build step; Chart.js is bundled locally (`static/vendor/`) so the dashboard works fully offline. |
| Data      | **openpyxl**                    | Reads the provided `GHG Sheet .xlsx` workbook directly during seeding. |
| Packaging | **Docker / docker-compose**     | Single `python:3.12-slim` image; `docker compose up` runs the whole stack. |

---

## 2. Database Schema (Data Modeling)

### 2.1 Entity-Relationship Diagram

```
┌──────────────────────────┐           ┌──────────────────────────────────┐
│   emission_factors       │           │        emission_records          │
│   (versioned master)     │           │   (one row per recorded event)   │
├──────────────────────────┤           ├──────────────────────────────────┤
│ id            PK         │◄──────────┤ factor_id              FK        │
│ scope         1|2|3      │  many:1   │ id                     PK        │
│ activity       e.g. Diesel│          │ scope, activity, section, plant  │
│ unit           e.g. KL    │           │ quantity, unit                   │
│ co2e_per_unit  kgCO2e/u   │           │ activity_date        ◄─ key      │
│ source         IPCC/CEA   │           │ factor_value_used   (snapshot)   │
│ valid_from     date       │           │ emissions_kgco2e    (calculated) │
│ valid_to       date|null  │           │ overridden (bool)                │
│ version        1,2,...    │           │ overridden_value_kgco2e          │
└──────────────────────────┘           │ created_at                       │
                                       └───────────────┬──────────────────┘
┌──────────────────────────┐                           │ 1:n
│    business_metrics      │           ┌───────────────▼──────────────────┐
├──────────────────────────┤           │            audit_log             │
│ id            PK         │           ├──────────────────────────────────┤
│ date          ◄─ key     │           │ id            PK                 │
│ metric_name   ◄─ key     │           │ record_id     FK → records       │
│ value         float      │           │ action        OVERRIDE|REVERT    │
│ unit          e.g. t     │           │ old_value_kgco2e                 │
└──────────────────────────┘           │ new_value_kgco2e                 │
                                       │ reason, changed_by, changed_at   │
                                       └──────────────────────────────────┘
```

### 2.2 Design Decisions

- **Versioned factors** (`emission_factors`): each activity can have multiple revisions (`version`), each with a validity window `[valid_from, valid_to]` (`valid_to = NULL` means "still current"). A partial index on `(activity, valid_from, valid_to)` makes date-based resolution fast. This supports both *historical accuracy* and *factor revisions over time*.
- **Immutable calculation snapshot** (`emission_records`): every record stores the resolved factor id, the factor value used, and the computed result, so any historical record remains reproducible even if master data changes later.
- **Canonical unit**: factors from the workbook are in `tCO2/unit`; the seed converts them to the GHG Protocol's standard **kgCO2e per unit** (`× 1000`) and the engine stores all results as `kgCO2e`.
- **Audit trail** (`audit_log`): every manual override *and* revert is captured with old value, new value, reason, author and timestamp.
- **Business metrics** (`business_metrics`): `{date, metric_name, value, unit}` — the denominator source for intensity analytics (e.g. *Tons of Steel Produced*, *Number of Employees*).
- **Scalability**: the schema is index-friendly and scope-agnostic; adding Scope 3 or new activities requires no schema change — only new master-data rows.

---

## 3. Core Calculation Logic

```
Activity Data (e.g. Liters of Diesel) × Emission Factor = GHG Emissions (kgCO2e)
```

**Historical accuracy** — the engine (`app/routers/engine.py`) resolves the factor that was valid **at the time the activity occurred**:

```sql
SELECT * FROM emission_factors
WHERE activity = :activity
  AND valid_from <= :activity_date
  AND (valid_to IS NULL OR valid_to >= :activity_date)
ORDER BY version DESC
LIMIT 1
```

The seed data deliberately includes **expired 2023 factors** (v1) alongside the current 2024 factors (v2), so this behavior is directly demonstrable:

```
GET /api/factors/resolve?activity=Diesel&on=2023-06-01   →  v1 (expired 2023 revision)
GET /api/factors/resolve?activity=Diesel&on=2024-06-01   →  v2 (current revision)
POST /api/records with activity_date=2022-...            →  422 (no factor valid)
```

---

## 4. API Reference

Interactive docs: **`http://localhost:8000/docs`** (Swagger UI, auto-generated by FastAPI).

### Records & Overrides (Milestone 3)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/records` | Create a Scope 1/2 (or 3) record. Body: `{scope, activity, section, plant, quantity, unit, activity_date}`. Engine resolves the factor valid on `activity_date` and computes `quantity × factor`. |
| `GET`  | `/api/records` | List records. Filters: `scope, start, end, activity, limit, offset`. |
| `PATCH`| `/api/records/{id}/override` | Manual override: `{new_value_kgco2e, reason, changed_by}`. Written to the audit log. |
| `DELETE`| `/api/records/{id}/override` | Revert an override back to the engine-calculated value (also audit logged). |
| `GET`  | `/api/audit-log` | Full audit trail. Filter: `record_id`. |
| `GET`  | `/api/factors` | Versioned master data. Filters: `scope, activity, valid_on`. |
| `GET`  | `/api/factors/resolve` | Shows which factor the engine would use: `?activity=Diesel&on=2024-03-15`. |

### Analytics (Milestone 2)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/analytics/yoy` | **YoY Emissions**: totals by Scope for the current and previous year (defaults to the latest year in the data; override-aware). Returns `change_pct` per scope. |
| `GET`  | `/api/analytics/intensity` | **Emission Intensity**: `kgCO2e` per unit of production for a period. Params: `start, end, metric` (BusinessMetric name, default *Tons of Steel Produced*), `scope`. |
| `GET`  | `/api/analytics/hotspot` | **Emission Hotspot**: breakdown of emissions by source with `% share`, sorted largest-first. Params: `start, end, scope`. |
| `GET`  | `/api/analytics/monthly` | Monthly totals per scope for a year (trend line). Params: `year, scope`. |

### Business Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/business-metrics` | List metrics. Filters: `metric_name, start, end`. |
| `GET`  | `/api/business-metrics/names` | Distinct metric names (powers the form dropdown). |
| `POST` | `/api/business-metrics` | Create: `{date, metric_name, value, unit}`. |

### Example: create a record and override it

```bash
# Scope 1 record — engine picks the factor valid on 2024-03-15
curl -X POST http://localhost:8000/api/records \
  -H "Content-Type: application/json" \
  -d '{"scope":1,"activity":"Diesel","section":"Rolling Mill","quantity":1000,"unit":"KL","activity_date":"2024-03-15"}'

# Manual override with audit trail
curl -X PATCH http://localhost:8000/api/records/1/override \
  -H "Content-Type: application/json" \
  -d '{"new_value_kgco2e":1600000,"reason":"Meter calibration correction","changed_by":"auditor.jane"}'

# View the audit trail
curl http://localhost:8000/api/audit-log?record_id=1
```

---

## 5. Seed Data

On first startup the app seeds the database from **`data/ghg_sheet.xlsx`** (the provided workbook):

| Table | Rows | Contents |
|-------|------|----------|
| `emission_factors` | 168 | 84 activities × 2 versions: an **expired 2023 revision** (v1, slightly different value) and the **current 2024 revision** (v2, exact workbook value). Scope 1 fuels/materials (IPCC 2006), Scope 2 electricity/steam (CEA India 2023), Scope 3 categories (GHG Protocol Scope 3 Eval Tool). |
| `emission_records` | ~1,090 | 2023 + 2024 records. Quarterly Scope 1 & 2 quantities are split evenly across the months of their quarter (giving the dashboard a monthly trend); Scope 3 is already monthly. All converted to kgCO2e. |
| `business_metrics` | 48 | *Tons of Steel Produced* and *Number of Employees*, monthly for 2023–2024. |
| `audit_log` | 1 | One sample override (with reason + author) so the feature is visible out of the box. |

All synthetic variation (2023 quantities, prior-year factor deltas) is **deterministic** (md5-derived), so re-seeding is reproducible.

> **Data-quality note:** the source workbook contains some unit inconsistencies (e.g. a `tCO2/t` factor applied to a material measured in `kNm3`), which inflate some Scope 1 magnitudes. The platform preserves the workbook data as-is and applies the sheet's own calculation convention (`quantity × factor`); flagging and normalizing such factors would be a natural next step (the versioned `emission_factors` table is designed for exactly that).

---

## 6. Frontend Dashboard (Milestone 4)

Single page (`static/index.html`) with all **four** mandatory ESG visualizations:

1. **Stacked Bar Chart** — YoY emissions comparison with separate stacks for Scope 1 and Scope 2 (ktCO2e).
2. **Donut Chart** — percentage breakdown of emissions by source (Emission Hotspot), top 8 sources + "Other".
3. **KPI Card** — core **Emission Intensity** metric (kgCO2e per ton of steel) plus total-emissions and per-scope KPI cards with YoY change.
4. **Line Chart** — total monthly emissions over the current year, per scope + total, to show trends.

Plus:
- **Scope 1/2 submission form** — activity dropdown driven by live master data, with a **factor preview** that shows exactly which factor version the engine will use for the chosen date (historical accuracy, visible in the UI).
- **Business metric form** — dropdown of existing metric names.
- **Records table** — recent records with inline **Override / Revert** actions.
- **Audit log table** — complete override history.

### Screenshots

**Dashboard — all four mandatory visualizations (stacked YoY bar, hotspot donut, intensity KPI cards, monthly trend line):**

![Dashboard](docs/screenshots/dashboard.png)

**Scope 1/2 form — the factor preview shows the engine will use the expired v1 (2023) factor for a 2023 activity date (historical accuracy):**

![Form](docs/screenshots/form-historical-accuracy.png)

**After submit — record saved with the v1 factor:**

![Form submitted](docs/screenshots/record-submitted.png)

**Records table with override action + Audit Log trail:**

![Audit](docs/screenshots/audit-trail.png)

**Auto-generated Swagger API docs:**

![Swagger](docs/screenshots/swagger-docs.png)

---

Chart.js is served locally from `static/vendor/` — no internet required.
---

## 7. Running the Project

### Option A — Docker (recommended)

Prerequisite: Docker Desktop (or a Docker engine) running.

```bash
cd ghg-platform

# Build the image
docker compose build

# Run (database is created and seeded automatically on first start)
docker compose up

# The platform is now available at:
#   Dashboard : http://localhost:8000
#   API docs  : http://localhost:8000/docs
```

The SQLite database persists on the host via the `./data` volume mount, so restarting the container keeps your records.

To reset to a fresh seeded state:

```bash
docker compose down
rm data/ghg_platform.db        # Windows: Remove-Item data\ghg_platform.db
docker compose up
```

### Option B — Local (no Docker)

Prerequisite: Python 3.10+.

```bash
cd ghg-platform

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# (optional) seed explicitly — the app also auto-seeds on startup
python -m app.seed

# run the server
uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000**.

### Option C — Hosted prototype: Vercel + Supabase (free tiers)

The app runs on Vercel as a Python serverless function (dashboard + API), with the database on **Supabase Postgres** — both free tiers, full persistence.

**Step 1 — Create the Supabase database**
1. Sign up at [supabase.com](https://supabase.com) and create a new project (any name/password).
2. Once created, go to **Project Settings → Database → Connection string → URI**.
3. Copy the **Connection pooling** URI (port `6543`) and replace `[YOUR-PASSWORD]` with the password you chose. Example:
   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
   ```

**Step 2 — Deploy to Vercel**
1. Sign up at [vercel.com](https://vercel.com) with your GitHub account.
2. **Add New → Project** → import the `Assignment-2` repository (framework preset: *Other* — auto-detected).
3. Before deploying, open **Settings → Environment Variables** and add:
   - `DATABASE_URL` = the Supabase URI from Step 1 (**required** — without it there is no persistent database)
4. Click **Deploy**.

**Step 3 — First load**
- Open `https://<your-project>.vercel.app` — the dashboard loads from the CDN.
- The **first API call** creates the schema in Supabase and seeds it from the bundled workbook (race-safe: concurrent cold starts cannot double-seed). This can take ~15–60 s on a cold start; subsequent calls are fast.
- API docs (Swagger): `https://<your-project>.vercel.app/api/index.py/docs`

> Local development needs no `DATABASE_URL` — the app falls back to SQLite automatically. Setting the env var switches to Postgres without any code change.

---

## 8. Project Structure

```
ghg-platform/
├── README.md                  ← this file (design + run docs)
├── requirements.txt
├── Dockerfile                 ← container packaging
├── docker-compose.yml         ← one-command run
├── vercel.json                ← Vercel config (function timeout + API rewrites)
├── .dockerignore
├── api/
│   ├── index.py               ← Vercel serverless entrypoint (serves app.main)
│   └── data/
│       └── ghg_sheet.xlsx     ← workbook bundled with the serverless function
├── data/
│   ├── ghg_sheet.xlsx         ← provided GHG workbook (seed source)
│   └── ghg_platform.db        ← SQLite DB (created at runtime, local/Docker)
├── app/
│   ├── main.py                ← FastAPI app, static hosting, auto-seed
│   ├── database.py            ← engine/session (SQLite or DATABASE_URL Postgres)
│   ├── models.py              ← ORM models (4 tables)
│   ├── schemas.py             ← Pydantic request/response models
│   ├── seed.py                ← workbook → DB seeding (race-safe)
│   └── routers/
│       ├── engine.py          ← calculation engine (historical accuracy)
│       ├── records.py         ← records, overrides, audit log, factors
│       ├── analytics.py       ← YoY, intensity, hotspot, monthly
│       └── metrics.py         ← business metrics CRUD
└── public/                    ← dashboard (Vercel CDN; served by FastAPI locally)
    ├── index.html             ← dashboard + forms
    ├── app.js                 ← fetch + Chart.js rendering
    ├── styles.css
    └── vendor/chart.umd.min.js
```

---

## 9. Mapping to Evaluation Criteria

| Milestone | Where it is implemented |
|-----------|------------------------|
| **M1 — System Design & Data Modeling (15)** | §1 architecture diagram & stack rationale; §2 schema with versioned factors + business metrics (`app/models.py`). |
| **M2 — Advanced Analytics & Reporting (45)** | `/api/analytics/yoy` (§M2.1), `/api/analytics/intensity` (§M2.2), `/api/analytics/hotspot` (§M2.3), historical accuracy in `app/routers/engine.py` + `/api/factors/resolve` + expired 2023 seed factors (§3). |
| **M3 — Core Backend API & Logic (15)** | `POST /api/records` for Scope 1 & 2 (§4), `PATCH/DELETE /api/records/{id}/override` with full `audit_log` trail (§4, visible in the dashboard's Audit Log table). |
| **M4 — Frontend & Visualization (25)** | §6 — Scope 1 form + business-metric form, and all four mandatory visualizations driven by the analytics endpoints. |
| **Packaging** | `Dockerfile` + `docker-compose.yml` (§7 A), local run (§7 B), hosted prototype on Vercel + Supabase (§7 C). |
