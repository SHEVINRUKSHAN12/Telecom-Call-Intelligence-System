# SQLite Migration Plan

## Goal

Replace MongoDB in this repo with SQLite while preserving the current backend API contract used by the frontend:

- `POST /api/calls`
- `GET /api/calls`
- `GET /api/calls/{call_id}`
- `GET /api/calls/{call_id}/audio-url`
- `GET /api/analytics`

This plan is specific to the current implementation in:

- `backend/routes/calls.py`
- `backend/services/mongodb.py`
- `backend/main.py`
- `backend/models/schemas.py`

The main risk-reduction principles are:

1. Keep the API response shape unchanged.
2. Use one main `calls` table first.
3. Store only frequently filtered/sorted fields as normal columns.
4. Store complex nested structures as JSON text.
5. Defer script/test cleanup until the main API works.

---

## 1. Proposed SQLite Schema For A Single Main Calls Table

Use one main table named `calls`.

Reasoning:

- The current production API reads and writes one call record at a time.
- Analytics only group by category and day.
- `speaker_segments`, `category.scores`, and `transcription_meta` are returned as nested structures but are not independently queried in production routes.
- A single table minimizes migration risk and code churn.

Recommended first-pass schema:

```sql
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,

  file_filename TEXT NOT NULL,
  file_content_type TEXT,
  file_size_bytes INTEGER NOT NULL,
  file_gcs_uri TEXT NOT NULL,
  file_blob_name TEXT,

  detected_language TEXT,
  duration_seconds REAL,
  full_transcript TEXT NOT NULL,
  search_text TEXT NOT NULL,

  category_label TEXT NOT NULL,
  category_confidence REAL NOT NULL DEFAULT 0,
  category_model TEXT,
  category_scores_json TEXT NOT NULL DEFAULT '{}',

  sentiment_label TEXT,
  sentiment_score REAL,
  sentiment_model TEXT,

  speaker_segments_json TEXT NOT NULL DEFAULT '[]',
  transcription_meta_json TEXT,

  CHECK (json_valid(category_scores_json)),
  CHECK (json_valid(speaker_segments_json)),
  CHECK (transcription_meta_json IS NULL OR json_valid(transcription_meta_json))
);
```

Notes:

- `id` should be an application-generated string id, not a SQLite integer row id.
- `created_at` should be stored as a UTC ISO-8601 string.
- `search_text` should contain searchable transcript text for fallback search and optional FTS population.
- This schema is enough for the current API and current repair scripts.

---

## 2. Exact Column List With Types

Exact recommended columns for `calls`:

| Column | Type | Required | Source |
| --- | --- | --- | --- |
| `id` | `TEXT` | yes | Mongo `_id` replacement |
| `created_at` | `TEXT` | yes | `record["created_at"]` |
| `file_filename` | `TEXT` | yes | `file.filename` |
| `file_content_type` | `TEXT` | no | `file.content_type` |
| `file_size_bytes` | `INTEGER` | yes | `file.size_bytes` |
| `file_gcs_uri` | `TEXT` | yes | `file.gcs_uri` |
| `file_blob_name` | `TEXT` | no | `file.blob_name` |
| `detected_language` | `TEXT` | no | `detected_language` |
| `duration_seconds` | `REAL` | no | `duration_seconds` |
| `full_transcript` | `TEXT` | yes | `full_transcript` |
| `search_text` | `TEXT` | yes | derived from transcript plus segment text |
| `category_label` | `TEXT` | yes | `category.label` |
| `category_confidence` | `REAL` | yes | `category.confidence` |
| `category_model` | `TEXT` | no | `category.model` |
| `category_scores_json` | `TEXT` | yes | `category.scores` |
| `sentiment_label` | `TEXT` | no | `sentiment.label` |
| `sentiment_score` | `REAL` | no | `sentiment.score` |
| `sentiment_model` | `TEXT` | no | `sentiment.model` |
| `speaker_segments_json` | `TEXT` | yes | `speaker_segments` |
| `transcription_meta_json` | `TEXT` | no | `transcription_meta` |

Recommended stored formats:

- `created_at`: ISO UTC string such as `2026-03-14T10:12:30.123456Z`
- `category_scores_json`: JSON object string
- `speaker_segments_json`: JSON array string
- `transcription_meta_json`: JSON object string

---

## 3. Field Mapping: Normal Columns vs JSON Text Columns

### Normal columns

These should be flattened into regular columns because the current routes sort, filter, group, or directly display them:

- `_id` -> `id`
- `created_at` -> `created_at`
- `file.filename` -> `file_filename`
- `file.content_type` -> `file_content_type`
- `file.size_bytes` -> `file_size_bytes`
- `file.gcs_uri` -> `file_gcs_uri`
- `file.blob_name` -> `file_blob_name`
- `detected_language` -> `detected_language`
- `duration_seconds` -> `duration_seconds`
- `full_transcript` -> `full_transcript`
- derived transcript search body -> `search_text`
- `category.label` -> `category_label`
- `category.confidence` -> `category_confidence`
- `category.model` -> `category_model`
- `sentiment.label` -> `sentiment_label`
- `sentiment.score` -> `sentiment_score`
- `sentiment.model` -> `sentiment_model`

Why these should be columns:

- `created_at` is used for sorting and date filtering.
- `category.label` is used for filtering and analytics grouping.
- `file_gcs_uri` is needed for `/calls/{call_id}/audio-url`.
- `full_transcript` and `search_text` support list previews and transcript search.
- sentiment/category summary fields are shown in list/detail responses.

### JSON text columns

These should remain JSON text because the current API returns them whole and does not query inside them in production routes:

- `category.scores` -> `category_scores_json`
- `speaker_segments` -> `speaker_segments_json`
- `transcription_meta` -> `transcription_meta_json`

Why JSON text is the cleanest first pass:

- `speaker_segments` is an ordered array of objects, which maps naturally to JSON.
- `category.scores` is a dynamic label-to-score map.
- `transcription_meta` is nested metadata that is currently returned as a whole object, not filtered in SQL.

### Not recommended for first pass

Do not split `speaker_segments` into a second table in the first migration.

Reason:

- The current routes do not query segments independently.
- Splitting segments into their own table increases migration and serialization complexity without helping the current API.

---

## 4. Recommended Indexes

Recommended indexes for the first migration:

```sql
CREATE INDEX IF NOT EXISTS idx_calls_created_at
ON calls (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_calls_category_created_at
ON calls (category_label, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_calls_detected_language
ON calls (detected_language);
```

Index purpose:

- `idx_calls_created_at`
  - supports default call history ordering
  - supports date range filtering

- `idx_calls_category_created_at`
  - supports `GET /api/calls?category=...`
  - still helps when results are sorted by newest first

- `idx_calls_detected_language`
  - preserves parity with the current Mongo index
  - not required by current routes, but low-cost and future-safe

No index is recommended on `full_transcript` if search is implemented with `LIKE`, because `%term%` will not use a normal B-tree index effectively.

---

## 5. Optional FTS5 Design For Transcript Search

Current Mongo behavior:

- `backend/routes/calls.py` uses Mongo `$text` search.
- The Mongo text index covers both `full_transcript` and `speaker_segments.text`.

SQLite equivalent:

Use FTS5 as an optional second step if transcript search quality/performance matters.

Recommended design:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS calls_fts
USING fts5(
  call_id UNINDEXED,
  search_text,
  tokenize = 'unicode61'
);
```

Recommended population strategy:

- Keep `calls.search_text` as the canonical search body.
- Populate `calls_fts.call_id` and `calls_fts.search_text` from application code when a call is inserted or updated.
- Avoid SQL triggers in the first pass unless needed.

Recommended search body:

- `full_transcript`
- plus all `speaker_segments[].text` joined into one string

Why this matches current behavior:

- Mongo indexed both transcript and segment text.
- A single `search_text` document preserves that behavior closely.

Fallback if FTS5 is deferred:

- Implement `q` filtering with:
  - `WHERE search_text LIKE '%' || ? || '%'`
- This is acceptable for a minimal first working version.
- It is not ideal for larger datasets.

---

## 6. Mapping Current Mongo Operations In `backend/routes/calls.py` To SQLite Equivalents

This section maps the current route logic directly.

### `insert_one`

Current Mongo usage:

- insert a complete `record` document
- receive `inserted_id`

SQLite equivalent:

- generate `id` in Python before insert
- run one `INSERT INTO calls (...) VALUES (...)`

Recommended id strategy:

- `uuid.uuid4().hex`
- or UUID string with hyphens

Recommended insert pattern:

```sql
INSERT INTO calls (
  id,
  created_at,
  file_filename,
  file_content_type,
  file_size_bytes,
  file_gcs_uri,
  file_blob_name,
  detected_language,
  duration_seconds,
  full_transcript,
  search_text,
  category_label,
  category_confidence,
  category_model,
  category_scores_json,
  sentiment_label,
  sentiment_score,
  sentiment_model,
  speaker_segments_json,
  transcription_meta_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

### `find` / `find_one`

Current Mongo usage:

- `list_calls()` uses `find(query)`
- `get_call()` uses `find_one({"_id": ObjectId(call_id)})`
- `get_call_audio_url()` uses `find_one({"_id": ObjectId(call_id)})`

SQLite equivalent:

- `find` -> `SELECT ... FROM calls WHERE ...`
- `find_one by id` -> `SELECT ... FROM calls WHERE id = ?`

Examples:

```sql
SELECT * FROM calls WHERE id = ?;
```

```sql
SELECT * FROM calls
WHERE created_at >= ?
  AND created_at <= ?
  AND category_label = ?
ORDER BY created_at DESC
LIMIT ?;
```

### `sort` / `limit`

Current Mongo usage:

- `.sort("created_at", -1).limit(limit)`

SQLite equivalent:

```sql
ORDER BY created_at DESC
LIMIT ?
```

### `aggregate`

Current Mongo usage in `/api/analytics`:

- group by `category.label`
- group by day derived from `created_at`

SQLite equivalent for category counts:

```sql
SELECT
  category_label AS category,
  COUNT(*) AS count
FROM calls
WHERE (? IS NULL OR created_at >= ?)
  AND (? IS NULL OR created_at <= ?)
GROUP BY category_label
ORDER BY count DESC;
```

SQLite equivalent for daily counts:

```sql
SELECT
  substr(created_at, 1, 10) AS date,
  COUNT(*) AS count
FROM calls
WHERE (? IS NULL OR created_at >= ?)
  AND (? IS NULL OR created_at <= ?)
GROUP BY substr(created_at, 1, 10)
ORDER BY date ASC;
```

### `count_documents`

Current Mongo usage:

- used in `list_calls()` and `get_analytics()`

SQLite equivalent:

```sql
SELECT COUNT(*) FROM calls WHERE ...;
```

### `ObjectId` usage

Current Mongo usage:

- `ObjectId(call_id)` validates the id format and queries `_id`

SQLite equivalent:

- no BSON conversion
- treat `call_id` as a plain text primary key
- route validation becomes:
  - if empty string or missing: reject
  - otherwise query by `id`

Result:

- remove `bson.ObjectId` dependency from the route layer
- keep the external API path format unchanged: `/api/calls/{call_id}`

---

## 7. Exact Implementation Order For Files

This order minimizes breakage while preserving the current API contract.

### Step 1: `backend/services/mongodb.py` replacement strategy

Recommended strategy:

- Keep the file path `backend/services/mongodb.py` for the first migration.
- Replace its internals with SQLite code instead of immediately renaming the file.

Why:

- `backend/main.py`
- `backend/routes/calls.py`
- several scripts/tests

already import this module. Keeping the same file path reduces churn in the first pass.

What this file should become in the first pass:

- SQLite connection helper
- schema/init function
- small data access helpers

Recommended functions:

- `get_db_path()`
- `init_db()`
- `insert_call(record)`
- `list_calls(...)`
- `get_call_by_id(call_id)`
- `get_call_audio_uri(call_id)`
- `get_analytics(start, end)`

What should be removed from this module:

- Motor client creation
- `AsyncIOMotorClient`
- `get_database()`
- `get_collection()`
- Mongo index creation logic

### Step 2: `backend/main.py` startup/init change

Current behavior:

- imports `init_indexes`
- calls it on startup

Change:

- replace `init_indexes()` with `init_db()`
- startup should create the `calls` table and indexes if missing
- startup should not attempt Mongo connections

### Step 3: `backend/routes/calls.py` route changes

This is the main migration file.

Recommended route conversion order inside this file:

1. `POST /calls`
   - replace document insert with SQLite insert
   - reconstruct response object in the current API shape

2. `GET /calls/{call_id}`
   - replace `ObjectId` lookup with text id lookup
   - rebuild nested response shape from flat columns plus JSON

3. `GET /calls/{call_id}/audio-url`
   - fetch only the stored GCS URI from SQLite

4. `GET /calls`
   - replace Mongo query building with SQL filter building
   - preserve:
     - `q`
     - `category`
     - `start`
     - `end`
     - `limit`

5. `GET /analytics`
   - replace Mongo pipelines with `GROUP BY` queries

Important:

- Keep response payload keys unchanged.
- Keep `backend/models/schemas.py` unchanged unless absolutely required.
- Reconstruct nested dictionaries before returning responses:
  - `file`
  - `category`
  - `sentiment`
  - `speaker_segments`
  - `transcription_meta`

### Step 4: `backend/requirements.txt` change

Recommended change:

- remove:
  - `motor`
  - `pymongo`
- add:
  - `aiosqlite`

Why `aiosqlite` is recommended:

- the existing route layer is async
- the replacement remains naturally async
- less manual thread-handling than raw `sqlite3`

### Step 5: `backend/.env.example` change

Current env file contains:

- `MONGODB_URI`
- `MONGODB_DB`
- `MONGODB_COLLECTION`

Recommended replacement:

```env
SQLITE_PATH=./data/calls.db
```

Optional additional envs:

```env
SQLITE_ENABLE_FTS=false
```

Migration guidance in comments should explain:

- SQLite is file-based
- the DB file path is relative to `backend/` if not absolute

---

## 8. Minimal First Working Version

The minimal first working version should aim only to make the production API work end to end.

Scope:

1. One `calls` table only
2. No second table for speaker segments
3. No frontend changes
4. No `backend/models/schemas.py` changes
5. Optional search can start with `LIKE` instead of FTS5

Recommended first-pass behavior:

- save calls to SQLite
- list calls from SQLite
- get call details from SQLite
- generate audio URLs using stored `file_gcs_uri`
- compute analytics from SQLite

Recommended simplifications for this phase:

- keep `speaker_segments` as JSON text
- keep `category.scores` as JSON text
- keep `transcription_meta` as JSON text
- use `search_text LIKE '%' || ? || '%'` for `q`

What this first version must preserve:

- same API endpoints
- same response keys
- same nested response shape
- same date filter behavior
- same newest-first call listing
- same category analytics output shape

---

## 9. Second Wave Cleanup

After the main API is stable on SQLite, update the repo’s scripts and tests.

### Scripts to update

- `backend/inspect_missing.py`
- `backend/list_all_calls.py`
- `backend/rebuild_transcripts.py`
- `backend/diagnose_call.py`
- `backend/backfill_sentiment.py`
- `backend/check_sentiment_structure.py`
- `backend/reclassify_all.py`

These currently depend on:

- `get_collection()`
- Mongo query syntax
- Mongo update operations such as `update_one`

Recommended cleanup approach:

- convert each script to use SQLite helper functions
- replace JSON field access with `json.loads(...)` where needed
- replace update logic with `UPDATE calls SET ... WHERE id = ?`

### Tests and diagnostics to update

- `backend/test_check_mongo_sentiment.py`
- `backend/test_mongo.py`
- `backend/test_api.py`

Recommended changes:

- remove direct Motor connection tests
- replace them with:
  - DB file initialization test
  - insert/select smoke test
  - API smoke tests against SQLite-backed routes

### Optional rename cleanup

Once the migration is stable, rename:

- `backend/services/mongodb.py`

to something accurate such as:

- `backend/services/db.py`
- or `backend/services/sqlite_store.py`

This rename should happen after the first working version, not during it.

### Docs cleanup

After code migration:

- update `README.md`
- remove MongoDB setup instructions
- replace Mongo env documentation with SQLite env documentation
- update architecture descriptions

---

## Recommended Final Decision

For this repo, the cleanest low-risk migration path is:

1. Use one SQLite `calls` table.
2. Flatten only the fields already used for filtering, sorting, grouping, or direct response rendering.
3. Store `speaker_segments`, `category.scores`, and `transcription_meta` as JSON text.
4. Keep the backend API contract unchanged.
5. Keep `backend/services/mongodb.py` in place during the first pass, but change its implementation to SQLite.
6. Defer script/test cleanup and any module renaming until after the main API is working.
