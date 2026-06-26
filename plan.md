# Plan: Offload Geometry Inspect + Repair Pipeline to a Background Task

## Problem

`create_new_model` (in `app/services/model_service.py`) runs the geometry
**inspect** and **repair** pipelines *synchronously inside the HTTP request*:

```
run_inspect_for_file_upload(...)   # slow: mesh inspect
run_repair_pipeline(...)           # slow: OBJ -> 3DM -> .geo -> .zip
```

For large models this exceeds Gunicorn's `timeout` (currently 120s, see
`gunicorn/gunicorn_config.py`). Symptoms observed:

```
[CRITICAL] WORKER TIMEOUT (pid:66)
Worker (pid:66) exited with code 1
db_service | unexpected EOF on client connection with an open transaction
```

When the worker is killed mid-request the open DB transaction is rolled back,
so the `Model`, `.geo` `File`, and both `ModelIssue` rows are **lost** even
though the repaired files were already written to `uploads/`.

## Goal

Move the inspect + repair work **off the request thread** so the
`POST /models` request returns immediately. The pipeline then runs in the
background and writes its results (issue reports + `ModelIssue` rows +
`repairStatus`) when finished. The frontend shows a loading state and polls
until the pipeline completes.

## Infrastructure Note: No Redis

This project's Celery does **not** use Redis. The broker and result backend are
**SQLite** (`config.py`):

```python
CELERY_CONFIG = {
    "broker_url":     "sqla+sqlite:///" + os.path.join(basedir, "celerydb.sqlite"),
    "result_backend": "db+sqlite:///"   + os.path.join(basedir, "celerydb.sqlite"),
}
```

The Celery app is built in `app/job_queue.py` (`make_celery`) and instantiated
in `app/__init__.py` as `celery`. The worker is started by `entrypoint.sh`:

```
celery -A $CELERY_APP worker --loglevel=info -P eventlet &
```

The existing solver flow already uses this exact pattern
(`run_solver = @shared_task` dispatched via `run_solver.delay(...)` in
`simulation_service.py`), so we mirror it. **No new services, no Redis.**

---

## Backend Changes

### 1. Add a new processing-status concept on `Model`

We need the frontend to know whether the pipeline is still running, finished,
or failed.

Add a `GeometryProcessingStatus` enum (`app/types/GeometryProcessingStatus.py`):

```python
from enum import Enum

class GeometryProcessingStatus(Enum):
    Pending = "Pending"        # queued, not started
    Processing = "Processing"  # inspect/repair running
    Completed = "Completed"    # finished successfully
    Failed = "Failed"          # pipeline raised
```

Register it in `app/types/__init__.py`.

Add a column to `Model` (`app/models/Model.py`):

```python
from app.types import GeometryProcessingStatus

geometryStatus = db.Column(
    db.Enum(GeometryProcessingStatus),
    nullable=True,
    default=None,   # None => no geo processing requested (feature off)
)
```

> NOTE: this is a new column => needs a DB migration (see "Migration" below),
> same class of change as `repairStatus` / `modelFileUrl`.

Expose it in `ModelInfoSchema` / `ModelSchema` (`app/schemas/model_schema.py`)
as a dump-only field so the frontend can read it:

```python
geometryStatus = fields.Function(
    lambda obj: obj.geometryStatus.value if obj.geometryStatus else None
)
```

### 2. Split `create_new_model` into "create row" + "dispatch task"

In `app/services/model_service.py`:

- `create_new_model` should:
  1. Create + commit the `Model` (with `outputFileId = sourceFileId`).
  2. If `FeatureToggle.is_enabled("enable_geo_conversion")` and the source
     file exists: create the `.geo` `File` row, set `new_model.hasGeo = True`,
     set `new_model.geometryStatus = GeometryProcessingStatus.Pending`, commit.
  3. Dispatch the background task: `process_model_geometry.delay(new_model.id)`.
  4. Return the model **immediately** (no pipeline work here).

- Remove the inline `run_inspect_for_file_upload` / `run_repair_pipeline` /
  `ModelIssue` creation from the request path.

### 3. New Celery task `process_model_geometry`

Add a task (either in `model_service.py` or a new
`app/services/geometry_tasks.py`) following the `run_solver` idiom — a fresh
scoped session, all errors caught, status updated at the end:

```python
from celery import shared_task
from sqlalchemy.orm import scoped_session, sessionmaker

@shared_task
def process_model_geometry(model_id: int):
    from app.db import db
    from app.models import Model, File, ModelIssue
    from app.types import DetectionStage, RepairStatus, GeometryProcessingStatus

    session = scoped_session(sessionmaker(bind=db.engine))()
    try:
        model = session.query(Model).get(model_id)
        if not model:
            return

        model.geometryStatus = GeometryProcessingStatus.Processing
        session.commit()

        file = session.query(File).get(model.sourceFileId)
        file_name, _ = os.path.splitext(os.path.basename(file.fileName))
        directory = DefaultConfig.UPLOAD_FOLDER

        # --- inspect (AfterUpload) ---
        _, issue_count = run_inspect_for_file_upload(file_name, directory)
        # build initial_issue_url + initial_model_url (use a configured host base,
        # NOT request.host_url — there is no request context in a worker; see note)
        session.add(ModelIssue(
            modelId=model.id,
            fileUrl=initial_issue_url,
            issueCount=issue_count,
            detectionStage=DetectionStage.AfterUpload,
            modelFileUrl=initial_model_url,
        ))

        # --- repair (AfterRepair) ---
        obj_path = os.path.join(directory, f"{file_name}.obj")
        _, remaining = run_repair_pipeline(obj_path, directory, volume_name="RoomVolume")
        session.add(ModelIssue(
            modelId=model.id,
            fileUrl=issue_url,
            issueCount=remaining,
            detectionStage=DetectionStage.AfterRepair,
            modelFileUrl=repaired_model_url,
        ))

        model.repairStatus = RepairStatus.Pending
        model.geometryStatus = GeometryProcessingStatus.Completed
        session.commit()
    except Exception as ex:
        session.rollback()
        try:
            model = session.query(Model).get(model_id)
            if model:
                model.geometryStatus = GeometryProcessingStatus.Failed
                session.commit()
        except Exception:
            session.rollback()
        logger.exception("process_model_geometry failed: %s", ex)
    finally:
        session.close()
```

### 4. Fix the URL building (no `request` in a worker)

`create_new_model` currently uses `request.host_url` to build
`initial_issue_url` / `modelFileUrl`. **There is no request context inside a
Celery task.** Replace with a configured base URL. Options:

- Add `PUBLIC_BASE_URL` (e.g. `http://localhost:5001`) to config / `.env.api`
  and build URLs as `f"{PUBLIC_BASE_URL}/{UPLOAD_FOLDER_NAME}/{filename}"`.
- Or reuse the existing `file_service.upload_dir()` helper which already builds
  `http://{FLASK_RUN_HOST}:{FLASK_RUN_PORT}/uploads` from env vars (no request
  needed) — preferred, since it is the same pattern used elsewhere.

> Capture the host base in `create_new_model` (where `request` IS available)
> and pass it to the task as an argument, OR use `file_service.upload_dir()`
> inside the task. Prefer `upload_dir()` to keep the task self-contained.

### 5. Migration

The new `geometryStatus` column requires a schema change. `flask create-db`
(`db.create_all()`) will NOT alter the existing `models` table.

Run one of:

```
flask db migrate -m "add geometryStatus to models"
flask db upgrade
```

or (dev only, drops data):

```
flask reset-db
```

### 6. Worker availability

Confirm the Celery worker is running (it is started by `entrypoint.sh`). The
SQLite broker means tasks are picked up by the same container's worker process.
No compose changes required. Redis stays unused.

### 7. Progress percentage (coarse / stage-based)

`repair_geometry` / `inspect_geometry` (in `geometry_service.py`) are atomic,
black-box calls, so we report a **coarse, stage-based** percent that the task
sets between the steps it already orchestrates. No changes to the
`geometry_pipeline` package.

Add a nullable `geometryProgress` integer column (0–100) on `Model` alongside
`geometryStatus`, and update it as the task advances:

```python
def _set_progress(session, model, pct):
    model.geometryProgress = pct
    session.commit()

# in process_model_geometry:
model.geometryStatus = GeometryProcessingStatus.Processing
_set_progress(session, model, 5)      # started

run_inspect_for_file_upload(...)
_set_progress(session, model, 35)     # inspect done

run_repair_pipeline(...)
_set_progress(session, model, 90)     # repair done

model.geometryStatus = GeometryProcessingStatus.Completed
_set_progress(session, model, 100)    # finished
```

Expose `geometryProgress` in `ModelInfoSchema` (plain `fields.Integer`). The
frontend already polls the model, so it reads the percent for free — no extra
endpoint. Numbers are approximate (the two heavy calls are opaque) but give a
real, monotonic progress bar.

---

## Frontend Changes

### Current behaviour

`GeometryRepairSidebar` / `GeometryIssueSidebar` read `model.issues` from
`useGetModelQuery`. With async processing, on first load the `issues` array and
`repairStatus` will be **empty/None** until the task finishes.

### 1. Read the new status

Add `geometryStatus` to the `ModelDetail` type
(`src/types/model.ts`):

```ts
geometryStatus?: "Pending" | "Processing" | "Completed" | "Failed" | null;
```

### 2. Poll while processing

In the model query (or in the repair/issue pages), enable polling while the
geometry is not finished. With RTK Query:

```ts
const { data: model } = useGetModelQuery(modelId, {
  pollingInterval:
    model?.geometryStatus === "Pending" || model?.geometryStatus === "Processing"
      ? 2000
      : 0,
});
```

(Or drive polling from a small wrapper hook so the interval stops once status is
`Completed` / `Failed`.)

### 3. Loading / error UI

In `GeometryRepairSidebar` and `GeometryIssuePage`:

- `geometryStatus === "Pending" | "Processing"` => show a spinner / skeleton
  ("Analyzing & repairing geometry…") and **hide/disable**:
  - Accept Repair / Undo Repair buttons (no repaired geometry yet)
  - the Possible Simulation panel (compatibility depends on the repaired report)
  - the remaining-issues list (not available yet)  - If the optional `geometryProgress` column is added (Backend 7A), render a
    progress bar from `model.geometryProgress` (0–100) instead of an
    indeterminate spinner. Add `geometryProgress?: number | null` to
    `ModelDetail`.- `geometryStatus === "Failed"` => show an error state with a message and (optionally) a retry action that re-dispatches the task.
- `geometryStatus === "Completed"` (or `null` when feature disabled) => render
  the current UI as today.

### 4. Disable simulation creation until ready

While `geometryStatus` is `Pending`/`Processing`, disable the `SimulationForm`
button (pass a `disabled` prop or wrap it) so users cannot start a simulation
on geometry that is still being processed or whose repair decision is pending.

### 5. Repair decision gating (already partially done)

`repairStatus` will be `null` until the task sets it to `Pending`. The existing
buttons already disable when `repairStatus === null`, so they will naturally
stay disabled during processing — just make sure the loading UI covers this
window.

---

## PR Strategy

The work is split into small, independently reviewable/mergeable PRs. Each PR
keeps `main`/`dev` in a working state. PRs 1–4 land on the backend repo
(`choras-org/backend`), PR 5 on the frontend repo
(`ajatdarojat45/choras-frontend`). The geometry-pipeline package is **not**
touched by any PR.

### PR 1 — Schema: status + progress columns (backend)

- Add `GeometryProcessingStatus` enum (`app/types/GeometryProcessingStatus.py`)
  + register in `app/types/__init__.py`.
- Add `Model.geometryStatus` and `Model.geometryProgress` columns (both nullable,
  default `None`).
- Add the Alembic migration (`flask db migrate` + `upgrade`).
- Expose `geometryStatus` (string) and `geometryProgress` (int) in
  `ModelInfoSchema` / `ModelSchema`.
- **No behaviour change yet** — columns stay `None`. Safe, tiny, reviewable.
- *Test:* migration applies cleanly; `GET /models/<id>` returns the two new
  null fields.

### PR 2 — Background task + dispatch (backend, core change)

- Add the `process_model_geometry` `@shared_task` (scoped session, error
  handling, coarse `_set_progress` updates 5 → 35 → 90 → 100).
- Fix URL building to not use `request` (use `file_service.upload_dir()`).
- Refactor `create_new_model` to commit the Model first, set
  `geometryStatus = Pending`, then `process_model_geometry.delay(model_id)` and
  return immediately. Remove the inline inspect/repair/ModelIssue work.
- *Test:* `POST /models` returns immediately (no worker timeout); model row
  persists; worker writes `ModelIssue` rows + sets status `Completed` +
  `repairStatus = Pending`; failure path sets `Failed`.
- Depends on PR 1.

### PR 3 — (optional) Retry / robustness (backend)

- Optional re-dispatch endpoint for `Failed` models
  (`POST /models/<id>/reprocess-geometry`) so the frontend "retry" can call it.
- Idempotency guard (don't double-create `ModelIssue` rows on re-run).
- Can be folded into PR 2 if small; kept separate to keep PR 2 focused.
- Depends on PR 2.

### PR 4 — Frontend types + polling (frontend)

- Add `geometryStatus` + `geometryProgress` to `ModelDetail`
  (`src/types/model.ts`).
- Add `pollingInterval` to `useGetModelQuery` while status is
  `Pending`/`Processing`, stopping at `Completed`/`Failed`.
- *Test:* model auto-refreshes until terminal state; no infinite polling.
- Depends on PR 1 (API shape) — can be developed in parallel with PR 2.

### PR 5 — Frontend loading/progress UI + gating (frontend)

- Progress bar from `geometryProgress` (spinner fallback) in
  `GeometryRepairSidebar` / `GeometryIssuePage`.
- Hide/disable Accept/Undo, Possible Simulation panel, issue list, and
  `SimulationForm` button while processing.
- `Failed` error state (+ retry if PR 3 landed).
- *Test:* full UX with a large model — loading → progress → results.
- Depends on PR 4 (and PR 2 for real data).

### Suggested merge order

`PR 1 → PR 2 → (PR 3) → PR 4 → PR 5`. PRs 1+2 already fix the worker-timeout and
data-loss bugs server-side; the frontend PRs add the UX on top.

## Out of Scope / Notes


- No Redis is introduced; the SQLite Celery broker is reused as-is.
- `eventlet` worker pool is fine for IO; if the geometry pipeline is CPU-bound
  and blocks the eventlet loop, consider a `-P prefork` worker or a dedicated
  queue — evaluate only if the single worker becomes a bottleneck.
- Progress is reported coarsely via a `geometryProgress` column updated between
  pipeline steps (Backend section 7); it requires no changes to the
  `geometry_pipeline` package. True per-step granularity would need a
  `progress_callback` added to `repair_geometry` / `inspect_geometry`, which is
  out of scope.
