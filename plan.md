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

## Known Limitations / Future Work

These are accepted trade-offs of the current implementation. They are fine for
single-user / low-concurrency use (e.g. demo, thesis) but should be revisited
before heavier multi-user load.

### 1. CPU-bound tasks on the eventlet pool are serialized (highest priority)

The Celery worker runs with `-P eventlet` (`entrypoint.sh`):

```bash
celery -A app.celery worker --loglevel=info -P eventlet &
```

Eventlet uses **greenlets** — many lightweight green threads on a **single OS
thread** that switch cooperatively, and only yield on **I/O waits**. This is
great for I/O-bound work.

But `repair_geometry` / `inspect_geometry` are **CPU/native-bound** (gmsh,
rhino3dm, mesh ops). They never hit an I/O wait, so they **never yield**. While
one geometry task runs, the single eventlet thread is fully blocked.

Consequences:

- **Geometry processing is effectively one-at-a-time.** Concurrent uploads
  queue behind each other even though the HTTP request returned instantly.
- **Other tasks are starved.** `run_solver` (simulations) shares the same
  worker/pool, so a long repair blocks queued simulations too.
- **Broker heartbeats can stall.** A long non-yielding task can delay Celery's
  heartbeat; the broker may consider the worker dead and **re-deliver the
  task**, risking double-processing of the same model.

Note: this is a *moved* bottleneck, not a new bug. The original problem
(blocking the gunicorn HTTP worker → request timeout + rolled-back transaction)
is fixed. The serialization now lives on the Celery side.

**Recommended fix:** run CPU-bound tasks on a **`prefork`** pool (separate OS
processes → true preemptive parallelism). Keep eventlet for I/O-ish tasks and
add a dedicated prefork worker + queue for geometry:

```bash
# existing I/O worker
celery -A app.celery worker -P eventlet -Q celery &
# dedicated CPU worker for geometry
celery -A app.celery worker -P prefork --concurrency=2 -Q geometry &
```

Then route the task to the `geometry` queue, e.g.
`process_model_geometry.apply_async(args=[model_id], queue="geometry")` (or via
`task_routes`). This lets geometry and simulations run independently and process
N models in parallel (`--concurrency=N`).

### 2. No task time limit / no auto-retry

`process_model_geometry` has no `soft_time_limit`/`time_limit`, so a hung
pipeline (bad geometry, gmsh loop) can block indefinitely — and with eventlet,
the whole worker. There is also no `autoretry_for`/`max_retries`; a transient
failure goes straight to `Failed` and relies on the manual retry button
(`POST /models/<id>/reprocess-geometry`).

**Why it matters:** without a ceiling, one pathological model can wedge the
worker forever (see #1 and #3). Without retries, a flaky/transient error (e.g. a
temporary file-lock or OOM blip) permanently marks an otherwise-fine model as
`Failed`.

**Recommended fix:** bound the runtime and auto-retry transient errors. Catch
`SoftTimeLimitExceeded` so the task can still mark the model `Failed` cleanly
before the hard limit kills it.

```python
from celery.exceptions import SoftTimeLimitExceeded

@shared_task(
    bind=True,
    soft_time_limit=600,     # 10 min: raises SoftTimeLimitExceeded (catchable)
    time_limit=660,          # 11 min: hard SIGKILL of the task
    autoretry_for=(Exception,),
    retry_backoff=True,      # 1s, 2s, 4s, ...
    max_retries=2,
    retry_jitter=True,
)
def process_model_geometry(self, model_id: int):
    ...
    except SoftTimeLimitExceeded:
        # mark Failed and DON'T re-raise so it isn't retried forever
        ...
```

Note: `autoretry_for=(Exception,)` will also retry the soft-timeout unless you
exclude it — either re-raise a non-retryable error type or `try/except
SoftTimeLimitExceeded` first and `return` after setting `Failed`. Pick limits
from the realistic worst-case pipeline duration for large models.

### 3. Models can get stranded in `Processing`

The model is committed *before* the heavy work (good — no more rollback data
loss). The inverse: if the worker is killed/restarted mid-task, the model is
left in `Processing`/`Pending` with nothing to flip it to `Failed`, and the
frontend polls forever.

**Why it matters:** container restarts/deploys are routine. Any model in flight
at that moment becomes a permanent zombie from the UI's perspective.

**Recommended fix (pick one or combine):**

- **Startup sweep** — on app boot, fail (or requeue) anything left mid-flight:

  ```python
  def recover_stuck_geometry():
      stuck = Model.query.filter(
          Model.geometryStatus.in_([
              GeometryProcessingStatus.Pending,
              GeometryProcessingStatus.Processing,
          ])
      ).all()
      for m in stuck:
          m.geometryStatus = GeometryProcessingStatus.Failed
      db.session.commit()
  ```

  Call it once from `create_app` (or an `entrypoint.sh` step) before the worker
  starts accepting work. Requeue instead of fail if you prefer auto-recovery.

- **TTL guard** — add an `updatedAt`-based check: treat `Processing` older than
  N minutes as `Failed`/eligible for reprocess (the frontend can surface this).

- **Acks-late** — `@shared_task(acks_late=True, reject_on_worker_lost=True)` so a
  task lost to a worker crash is redelivered by the broker (combine with #1's
  prefork + idempotency, which already clears prior `ModelIssue` rows).

### 4. Lost-update race on the `Model` row

The task writes the model via its own `scoped_session` while HTTP requests
(`set_repair_decision`, `update_model`) write the same row via `db.session`,
with no row locking. A user action during processing could clobber the task's
write, or vice-versa (last-commit-wins).

**Why it matters:** e.g. a user clicks *Accept Repair* just as the task sets
`repairStatus = Pending` / `geometryStatus = Completed`; one commit overwrites
the other and the row ends up inconsistent (status says done, decision lost —
or vice versa). The `Processing` guard in `reprocess_model_geometry` narrows the
window but does not close it.

**Recommended fix (pick one):**

- **Row lock** the model when mutating it, so concurrent writers serialize:

  ```python
  model = (
      session.query(Model)
      .filter_by(id=model_id)
      .with_for_update()      # SELECT ... FOR UPDATE (Postgres)
      .one()
  )
  ```

- **Status guard on user actions** — reject accept/reject while not `Completed`:

  ```python
  if model.geometryStatus in (
      GeometryProcessingStatus.Pending,
      GeometryProcessingStatus.Processing,
  ):
      abort(409, message="Geometry is still processing")
  ```

  The frontend already hides these buttons during processing (PR 5), so this is
  mainly defense-in-depth against direct API calls.

- **Narrow writes** — have the task only update the geometry/repair columns it
  owns, never blindly overwrite the whole row, to minimize the blast radius.

### 5. SQLite Celery broker concurrency

The broker/result backend is a single SQLite file (`celerydb.sqlite`) with a
global write lock. Under several simultaneous uploads (plus the 4× progress
commits per task) it can hit `database is locked`. Fine for low concurrency;
move to a real broker if load grows.

### 6. Cosmetic progress + perceived latency

The 5/35/90/100 markers are coarse stage flags, not real progress — the bar
sits at 35% during the longest (repair) phase. Also, even tiny models now go
through Pending→Processing→Completed with a loading state instead of returning
instantly. Accepted trade-off.

