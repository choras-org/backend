# CHORAS Testing Strategy
## CHORAS Scalability Project - EngD 2026

---

## 1. Overview

This document defines the testing strategy for the CHORAS simulation platform.
Unlike traditional web applications, CHORAS integrates heavy computational
simulation methods that must be containerized and executed across distributed
environments (local Docker, cloud, and HPC). Testing must therefore go beyond
functional correctness and address container isolation, distributed execution,
scalability, and reproducibility.

---

## 2. Testing Philosophy

Testing in CHORAS follows an incremental, understanding-first approach across
three stages:

1. **Explore** — the existing codebase and runtime behavior are studied before
   writing any tests, to ensure tests reflect actual rather than assumed behavior.
2. **Implement and test in parallel** — as new behavior is introduced during
   re-architecture, corresponding tests are written alongside it rather than
   after the fact.
3. **Deepen and diversify** — once baseline coverage is established, test cases
   are systematically expanded using equivalence partitioning and boundary value
   analysis to uncover edge cases and drive further optimization.

---

## Test Risk Justification

For our tests we have decided to focus primarily on integration tests, with
some unit tests being done as well. As we are constrained in terms of time
and inputs to test against, we felt that doing integration tests that cover
the majority of the behavior of the project will be far more suitable for
our timeline.

### Why Integration Tests Are Prioritised

The core risk in this system lies at the boundaries between components,
specifically how `simulation_service` routes to the correct executor, how
`LocalExecutor` and `CloudExecutor` handle real Docker and SSH interactions,
and how the post-processing pipeline behaves after a job completes. These
risks are not detectable by unit tests alone, making integration tests the
highest-value investment for our scope.

Unit tests are included where the logic is self-contained and failure would
be silent or misleading (e.g. `_parse_overall_progress`, `executor_factory`,
the auralization match block).

### What Is Explicitly Excluded and Why

**Mesh generation, REST API layer, and acoustic output accuracy** — these
are part of the foundation codebase provided to us. We treat them as
verified externally and out of our testing responsibility.

**Cancellation end-to-end and frontend/discovery integration** — these are
covered by manual testing performed separately. Automating these would
require a running frontend and a live Celery worker, which we do not have
time to implement within this project phase.

**Concurrent simulations** — identified as out of scope for this project
phase. The risk is acknowledged but deferred.

**Real database integration testing** — database behaviour is verified at
the service layer only, using mocked sessions to test how `run_solver()`
handles database failure scenarios. Actual schema validation, ORM constraint
enforcement, and migration correctness are out of scope for this phase.

**`_connect()` / `_disconnect()` SSH connection management** — these methods
were considered during test design but will not be implemented in the current
architecture. The existing `_ssh_session()` context manager pattern is
sufficient for the current scope.

### Residual Risks

The following known gaps remain after our test suite:

- **DEF-001** — No timeout exists in `_poll_until_complete` — a silently
  crashed remote job will cause indefinite polling. This is the highest
  residual risk and is flagged as a bug to fix rather than a test to defer.
- **DEF-002** — No `POLL_MAX_FAILED_CYCLES` limit — a permanently corrupt
  remote JSON file will cause the polling loop to run forever.
- **DEF-003** — `container.wait()` exit codes are not checked — a failed
  local simulation can be silently marked as Completed.
- **DEF-004** — `raise "Error saving..."` in the export failure path is
  invalid Python — raises `TypeError` instead of a meaningful error message.
  **DEF-005** - SSH failure mid-execute leaves remote sandbox unclean and does not remove it
- **DEF-006** — New simulation methods beyond DE and DG silently skip
  auralization due to an incomplete `match` block.
  **DEF-007** - The functions in the cloud executor assume that the outputs made
  by the simmulation methods will be .json and .csv files only. Thus the download 
  function will download all the .json and .csv files that are present in the remote 
  sandbox. New simmulation methods that make other output files but dont have an extension of 
  .json or .csv will not be downloaded. Also .json and .csv files that may not be output files 
  will also be downloaded by the local machines from the remote machine
  **DEF-008** - When making the key associated with your cloud account ensure that there is no passphrase made with it. CHORAS Backend fully supports cloud accounts/keys that have passphrases associated with them. However a future development is to find a way to ensure that the passphrase assoicated with the cloud account/key is **passed** to the CHORAS backend


All residual risks are documented in the Defect Log in `Test Results.md`
and are prioritised for resolution before production use.

---

## 3. Test Design Approach

The primary test design technique used in CHORAS is **equivalence
partitioning**, supplemented by **boundary value analysis** at partition
edges. Equivalence partitioning ensures that the test suite is comprehensive
without being redundant, by identifying groups of inputs or system states
that the platform should handle identically — meaning one representative
case per partition is sufficient to expose defects in that class. Boundary
value analysis then targets the edges between partitions, where defects are
statistically most likely to occur.

EP and BVA determine *what data* to use; TestCompass determines *which
behavioral paths* to exercise with that data.

---

## 4. Equivalence Partitions

### 4.1 Simulation Method

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-M1 | Computationally cheap method | `DE` |
| EP-M2 | Computationally expensive method | `DG` |
| EP-M3 | User-added new method | `MyNewMethod` |
| EP-M4 | Method not registered in discovery | `"UnknownMethod"` |
| EP-M5 | Method registered in config but `container_image` is `None` | `discover_container_image` returns `None` |
| EP-M6 | Method registered in config but `entry_file` is `None` | `discover_entry_file` returns `None` |

---

### 4.2 Execution Environment (ResourceType)

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-E1 | Local execution (Docker) | `ResourceType.Local` |
| EP-E2 | Cloud execution (Singularity over SSH) | `ResourceType.Cloud` |
| EP-E3 | Invalid / unsupported resource type | `"GPU"`, `None` |

---

### 4.3 Input Geometry (.obj file)

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-G1 | Simple geometry | `MeasurementRoom.obj` |
| EP-G2 | Moderately complex geometry | `Room2215_simple.obj` |
| EP-G3 | Complex geometry with absorption | `Room2215_withAbs.obj` |

---

### 4.4 Simulation Configuration (`sim_config`)

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-C1 | Valid config with all required fields | `{"env": {"JSON_PATH": "/app/uploads/task1/input.json"}}` |
| EP-C2 | `JSON_PATH` missing from env | `{"env": {}}` |
| EP-C3 | `JSON_PATH` points to non-existent file | `{"env": {"JSON_PATH": "/app/uploads/missing.json"}}` |
| EP-C4 | `JSON_PATH` exists but file is unreadable (permissions) | `{"env": {"JSON_PATH": "/app/uploads/locked.json"}}` |
| EP-C5 | `JSON_PATH` exists but file is malformed JSON | `{"env": {"JSON_PATH": "/app/uploads/corrupt.json"}}` |
| EP-C6 | `solverSettings` is `None` | `simulation.solverSettings = None` |
| EP-C7 | `solverSettings` is malformed | `simulation.solverSettings = {"bad": "data"}` |

---

### 4.5 Docker / Local Executor State

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-D1 | Docker daemon running, image present | Normal setup |
| EP-D2 | Docker daemon is down | `docker.from_env()` raises |
| EP-D3 | Container name already in use (duplicate run) | Same `simulation_id` run twice |
| EP-D4 | Host mount path cannot be resolved | No matching mount in `get_host_path_for_container_path` |
| EP-D5 | Container exits with non-zero status code | `container.wait()` returns `{"StatusCode": 1}` |

---

### 4.6 SSH / Cloud Executor State

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-S1 | SSH connection healthy, all operations succeed | Normal cloud setup |
| EP-S2 | SSH authentication fails | `paramiko.AuthenticationException` |
| EP-S3 | SSH connection times out | `socket.timeout` |
| EP-S4 | SFTP upload fails mid-transfer | Network drop during `sftp.put` |
| EP-S5 | Remote disk full (Singularity build fails) | `SSHCommandError` on `_build_singularity_image` |
| EP-S6 | Remote sandbox already exists from a previous failed run | `_build_singularity_image` behaves unexpectedly |

---

### 4.7 Remote Job Progress (Polling)

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-P1 | Progress increments normally and reaches 100% | `percentage`: 0 → 50 → 100 |
| EP-P2 | Progress reaches 100% on first poll | `percentage`: 100 immediately |
| EP-P3 | Remote JSON is temporarily corrupt (recovers within retries) | Corrupt on attempt 1, valid on attempt 2 |
| EP-P4 | Remote JSON is corrupt across all 3 retries every cycle | Never readable → infinite loop (DEF-002) |
| EP-P5 | Remote simulation crashes silently, progress never reaches 100% | Stuck at e.g. 50% forever → infinite loop (DEF-001) |
| EP-P6 | Cancel flag created before polling starts | `{task_id}.cancel` file exists at poll entry |
| EP-P7 | Cancel flag created mid-polling | `{task_id}.cancel` file created after cycle 2 |

---

### 4.8 Database State

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-DB1 | `SimulationRun` exists in DB | Normal run |
| EP-DB2 | `SimulationRun` not found in DB | `session.query(SimulationRun).get(id)` returns `None` |
| EP-DB3 | `Simulation` not found for a valid `SimulationRun` | `filter_by(simulationRunId=...)` returns `None` |
| EP-DB4 | DB commit fails | `session.commit()` raises `SQLAlchemyError` |

> **Scope note:** These partitions are tested at the **service layer only**
> using mocked sessions. Tests verify how `run_solver()` responds to
> different database return values and exceptions — they do not test the
> database itself. Real database integration testing (schema validation,
> constraint enforcement, migration correctness) is explicitly out of scope
> for this project phase.

---

### 4.9 Output and Post-Processing

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-O1 | Output JSON and CSV present after completion | Normal completion |
| EP-O2 | Output JSON missing after completion | No `.json` in remote `/app` dir |
| EP-O3 | `ExportHelper.parse_json_file_to_xlsx_file` succeeds | Returns `True` |
| EP-O4 | `ExportHelper.parse_json_file_to_xlsx_file` fails | Returns `False` → `raise "Error..."` (invalid Python — DEF-004) |
| EP-O5 | `auralization_calculation` succeeds (DE) | WAV file written |
| EP-O6 | `auralization_calculation_DG` succeeds (DG) | WAV file written |
| EP-O7 | `auralization_calculation` raises after XLSX already written | Partial export left in DB |
| EP-O8 | `simulation_method` is not `DE` or `DG` | `match` falls through, no auralization, no error (DEF-006) |

---

### 4.10 Discovery Service

| Partition ID | Class | Representative Value |
|---|---|---|
| EP-DS1 | All methods well-formed in repo | All appear correctly in frontend |
| EP-DS2 | New method added to repo | Appears in frontend after discovery |
| EP-DS3 | Existing method removed from repo | Disappears from frontend after discovery |
| EP-DS4 | Method definition malformed (e.g. missing `entryFile`) | Discovery does not crash, valid methods still shown |
| EP-DS5 | Zero methods in backend | Frontend shows empty list, no crash |

---

## 5. Test Coverage Summary

The following table maps each equivalence partition to its coverage status
after the full test suite has been implemented.

| Partition | Covered | Test File | Notes |
|---|---|---|---|
| EP-M1 | ✅ | `test_local_executor_final.py` | |
| EP-M2 | ✅ | `test_local_executor_final.py`, `test_cloud_executor_final.py` | |
| EP-M3 | ✅ | `test_local_executor_final.py` | |
| EP-M4 | ✅ | `test_remaining_cases.py` | |
| EP-M5 | ✅ | `test_executor_factory.py`, `test_discovery_service.py` | |
| EP-M6 | ✅ | `test_executor_factory.py`, `test_remaining_cases.py` | |
| EP-E1 | ✅ | `test_local_executor_final.py` | |
| EP-E2 | ✅ | `test_cloud_executor_final.py` | |
| EP-E3 | ✅ | `test_executor_factory.py` | |
| EP-G1 | ✅ | `test_local_executor_final.py` | |
| EP-G2 | ✅ | `test_local_executor_final.py` | |
| EP-G3 | ✅ | `test_local_executor_final.py` | |
| EP-C1 | ✅ | `test_cloud_executor_final.py`, `test_local_executor_final.py` | |
| EP-C2 | ✅ | `test_local_executor.py` | |
| EP-C3 | ✅ | `test_run_solver.py` | |
| EP-C4 | ✅ | `test_run_solver.py` | |
| EP-C5 | ✅ | `test_cloud_executor_final.py` | |
| EP-C6 | ✅ | `test_run_solver.py` | |
| EP-C7 | ✅ | `test_run_solver.py` | |
| EP-D1 | ✅ | `test_local_executor_final.py` | |
| EP-D2 | ✅ | `test_local_executor.py`, `test_local_executor_final.py` | |
| EP-D3 | ✅ | `test_local_executor.py` | |
| EP-D4 | ✅ | `test_local_executor.py`, `test_local_executor_final.py` | |
| EP-D5 | ✅ | `test_local_executor.py`, `test_run_solver.py` | Known bug DEF-003 |
| EP-S1 | ✅ | `test_cloud_executor_final.py`, `test_missing_cases.py` | |
| EP-S2 | ✅ | `test_cloud_executor.py`, `test_cloud_executor_final.py` | |
| EP-S3 | ✅ | `test_cloud_executor_final.py` | |
| EP-S4 | ✅ | `test_cloud_executor.py`, `test_cloud_executor_final.py` | |
| EP-S5 | ✅ | `test_cloud_executor_final.py`, `test_missing_cases.py` | |
| EP-S6 | ✅ | `test_cloud_executor.py`, `test_cloud_executor_final.py` | |
| EP-P1 | ✅ | `test_cloud_executor_final.py` | |
| EP-P2 | ✅ | `test_cloud_executor_final.py` | |
| EP-P3 | ✅ | `test_cloud_executor_final.py` | |
| EP-P4 | ✅ | `test_cloud_executor_final.py` | xpassed — DEF-002 |
| EP-P5 | ✅ | `test_cloud_executor_final.py` | xpassed — DEF-001 |
| EP-P6 | ✅ | `test_cloud_executor_final.py` | |
| EP-P7 | ✅ | `test_cloud_executor_final.py` | |
| EP-O1 | ✅ | `test_cloud_executor_final.py`, `test_missing_cases.py` | |
| EP-O2 | ⚠️ Not tested | — | Out of scope — no remote file missing scenario implemented, due to time constraint |
| EP-O3 | ⚠️ Not tested | — | Happy path export not directly tested, out of scope |
| EP-O4 | ✅ | `test_run_solver.py` | Known bug DEF-004 |
| EP-O5 | ⚠️ Not tested | — | Auralization success path out of scope |
| EP-O6 | ⚠️ Not tested | — | Auralization success path out of scope |
| EP-O7 | ✅ | `test_run_solver.py` | |
| EP-O8 | ⚠️ Commented out | `test_run_solver.py` | Known bug DEF-006 |
| EP-DB1 | ✅ | Implicit in all `test_run_solver.py` tests | Mocked session |
| EP-DB2 | ✅ | `test_run_solver.py` | Service layer only — mocked |
| EP-DB3 | ✅ | `test_run_solver.py` | Service layer only — mocked |
| EP-DB4 | ✅ | `test_remaining_cases.py` | Service layer only — mocked |
| EP-DS1 | ✅ | `test_discovery_service.py` | |
| EP-DS2 | ⚠️ Implicit | `test_discovery_service.py` | MyNewMethod present in real config |
| EP-DS3 | ✅ | `test_remaining_cases.py` | |
| EP-DS4 | ✅ | `test_discovery_service.py` | |
| EP-DS5 | ⚠️ Not tested | — | Implicit |

---

## 6. Testing Pillars

### 6.1 Functional Correctness
Ensures all API endpoints and simulation logic behave correctly, covering
backend unit tests, API integration tests, Celery task validation, and
input/output schema validation.

### 6.2 Simulation Contract Testing
Each simulation container must comply with a strict interface contract:
accepting standardized input, returning standardized output, respecting
exit code conventions, operating within resource limits, avoiding filesystem
side effects, and producing reproducible results. This ensures new simulation
methods can be added without modifying the core backend.

### 6.3 Container Isolation
Simulation containers must not access the host filesystem, must not access
other simulation containers, must respect memory and CPU limits, and must
run independently of the backend service.

### 6.4 Distributed Execution
Validates the Celery-based distributed processing layer, including task
queue latency, worker crash recovery, retry mechanisms, and concurrent
simulation execution.

### 6.5 Performance and Scalability
Evaluates system behavior under load, measuring parallel simulation
capacity, container startup time, queue throughput, runtime under concurrent
load, and memory usage per simulation. Performance regressions exceeding
10% trigger investigation.

### 6.6 Cloud and HPC Execution
Validates deployment on remote infrastructure, including remote job
submission, data persistence in object storage, network latency tolerance,
failure recovery, and consistency of results between cloud and local
execution.

### 6.7 Reproducibility
For research validity, simulations must produce consistent outputs:
identical inputs must yield identical outputs within a defined numerical
tolerance, deterministic seeds must be applied where applicable, and
dependencies must be version-locked.

---

## 7. Architectural Testing Principles

1. Simulation methods must be isolated — a fault in one method must not
   affect others.
2. Adding a new simulation method must not require modification of the
   backend core.
3. Containers must be self-contained and free of external side effects.
4. Cloud execution must mirror local execution in terms of correctness and
   output.
5. Scalability must be measurable and tracked across releases.

---

## 8. Continuous Integration

The CI pipeline runs automatically on every push and pull request to
protected branches (`main`, `dev`, `feature/*`, `bugfix/*`, `testing/*`).

**CI environment:**
- GitHub Actions · Ubuntu Latest · Python 3.10
- PostgreSQL 15 service container (replaces SQLite for test database)
- Mock `methods-config.json` and settings files created at runtime since
  `simulation-backend` is not present as a submodule in CI

**CI verifies that:**
- All unit and integration tests pass
- Docker images build successfully
- Container smoke tests pass
- Performance results are within the accepted baseline threshold

**Current CI results (2026-03-17):**

| Metric | Value |
|---|---|
| Total collected | 120 |
| Passed | 116 |
| Failed | 0 |
| xfail | 1 |
| xpassed | 2 |
| Duration | ~7s |

---

## 9. Release Criteria

A release is approved only if all of the following conditions are met:

- All contract tests pass
- Parallel execution has been validated
- Celery load tests pass
- Container isolation is verified
- Cloud execution has been tested successfully
- Reproducibility is confirmed across all deterministic methods
- No performance regression exceeds 10%
- All critical and high-severity defects are resolved or formally accepted
- The requirements traceability matrix confirms full verification coverage

---

**Last Updated:** March 2026
**Maintained by:** Test Manager
**Related documents:** `Test Design v6.md`, `Test Results v2.md`