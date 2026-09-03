# CHORAS — Test Design Document
## All Test Files · Full Coverage
### CHORAS Scalability Project - EngD 2026

**Version:** 6.0
**Status:** Draft
**Date:** 2026-03-17
**Related Documents:** `Testing Strategy.md`, `Test Results.md`
**Maintained by:** Test Manager

---

## 1. Purpose

This document defines how every test case across all CHORAS test files is
designed. For every test it specifies:

- **What is being tested** — the component and behaviour under scrutiny
- **Inputs** — the exact data, configuration, and system state passed in
- **Process** — the steps taken to execute the test
- **Expected Output** — the observable result that determines pass or fail
- **Equivalence Partition(s) covered** — tracing each test back to the
  partitions defined in the Testing Strategy

---

## 2. Test Files and Scope

| File | Component(s) Tested | Type |
|---|---|---|
| `test_cloud_executor.py` | `CloudExecutor` — bad day via `execute()` | Integration |
| `test_cloud_executor_final.py` | `CloudExecutor` — all internal methods | Unit + Integration |
| `test_local_executor.py` | `LocalExecutor` — bad day via `execute()` | Integration |
| `test_local_executor_final.py` | `LocalExecutor` — all internal methods | Unit + Integration |
| `test_missing_cases.py` | Helper functions, `_CompletedJob`, `__init__` methods | Unit + Integration |
| `test_executor_factory.py` | `executor_factory()` routing and edge cases | Unit + Integration |
| `test_discovery_service.py` | `discovery_service.py` — all discovery functions | Unit |
| `test_run_solver.py` | `simulation_service.py → run_solver()` | Unit + Integration |
| `test_remaining_cases.py` | EP-DB4, EP-DS3, EP-M4 gap coverage | Unit + Integration |

---

## 3. Test Case Naming Convention

| Prefix | Type | Description |
|---|---|---|
| `U` | Unit | Pure logic, no external dependencies |
| `I` | Integration | Happy path, real component interactions |
| `B` | Bad Day | Failure and edge case scenarios |
| `RS` | Run Solver | Tests for `simulation_service.run_solver()` |
| `DS` | Discovery | Tests for `discovery_service.py` |
| `EF` | Executor Factory | Tests for `executor_factory()` |
| `REM` | Remaining | Gap coverage tests |

---

## 4. `test_cloud_executor.py` — Bad Day Tests

**Purpose:** Verifies exception propagation through the full `execute()` flow
when individual steps fail. These are the original bad day tests and remain
unchanged.

| Test | Partition | Scenario | Expected Output |
|---|---|---|---|
| `test_ssh_authentication_fails` | EP-S2 | `paramiko.AuthenticationException` during `connect()` | `SSHCommandError` matching `"SSH authentication failed"` |
| `test_sftp_upload_tar_fails_halfway` | EP-S4 | `sftp.put` raises mid-transfer | `Exception` matching `"SFTP upload interrupted"` |
| `test_build_singularity_image_fails` | EP-S5 | `_build_singularity_image` raises `"Disk full"` | `Exception` matching `"Disk full"` |
| `test_remote_json_never_reaches_100` | EP-P5 | `_poll_until_complete` raises `"Timeout"` | `Exception` matching `"Timeout"` |
| `test_remote_json_always_corrupt` | EP-P4 | `json.load` raises `JSONDecodeError` on every attempt | `Exception` matching `"Timeout"` via sleep mock |
| `test_cancel_flag_created_before_polling` | EP-P6 | `_should_cancel` returns `True` before first download | `_CompletedJob` returned · `_download_file_via_sftp` never called |
| `test_collect_outputs_and_cleanup_fails_mid_download` | EP-S4 | `_poll_until_complete` raises `"Network error"` | `Exception` matching `"Network error"` |
| `test_build_fails_when_remote_sandbox_already_exists` | EP-S6 | `_build_singularity_image` raises `"sandbox already exists"` | `Exception` matching `"sandbox already exists"` |

---

## 5. `test_cloud_executor_final.py` — Full CloudExecutor Coverage

### 5.1 `_parse_overall_progress` Tests (U1–U5)

| Test | Partition | Input | Expected Output |
|---|---|---|---|
| U1 `test_multiple_results_returns_minimum` | EP-P1 | `[{80}, {40}, {60}]` | `40` |
| U2 `test_single_result_at_100` | EP-P2 | `[{100}]` | `100` |
| U3 `test_empty_results_list_returns_none` | EP-C5 | `{"results": []}` | `None` |
| U4 `test_results_entry_missing_percentage_key` | EP-C5 | `[{"no_percentage": 1}]` | `0` |
| U5 `test_results_is_not_a_list_returns_none` | EP-C5 | `{"results": "not_a_list"}` | `None` |

---

### 5.2 `get_filenames` Tests (U6–U8)

---

#### U6 — `get_filenames`: extracts msh and geo filenames and updates JSON in place

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → get_filenames()` |
| **Partitions** | EP-C1 |
| **What is being tested** | Full absolute paths stripped to filenames only; JSON file updated in place |
| **Input** | `{"msh_path": "/app/uploads/sim1/room.msh", "geo_path": "/app/uploads/sim1/room.geo"}` |
| **Process** | 1. Write JSON to temp file · 2. Call `get_filenames()` · 3. Assert return values · 4. Re-read file and assert updated values |
| **Expected Output** | Returns `("room.msh", "room.geo")` · JSON contains filenames only |
| **Pass Criteria** | Both return values and both JSON values are filenames without path separators |

---

#### U7 — `get_filenames`: missing `msh_path` raises `KeyError`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → get_filenames()` |
| **Partitions** | EP-C5 |
| **What is being tested** | JSON missing `msh_path` → `KeyError` raised |
| **Input** | `{"geo_path": "/app/uploads/sim1/room.geo"}` |
| **Expected Output** | `KeyError` raised |
| **Pass Criteria** | `pytest.raises(KeyError)` passes |

---

#### U8 — `get_filenames`: missing `geo_path` raises `KeyError`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → get_filenames()` |
| **Partitions** | EP-C5 |
| **What is being tested** | JSON missing `geo_path` → `KeyError` raised |
| **Input** | `{"msh_path": "/app/uploads/sim1/room.msh"}` |
| **Expected Output** | `KeyError` raised |
| **Pass Criteria** | `pytest.raises(KeyError)` passes |

---

### 5.3 `_should_cancel` Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| `test_returns_false_when_no_cancel_flag` | EP-P1 | Cancel flag file absent | `False` |
| `test_returns_true_when_cancel_flag_exists` | EP-P6 | Cancel flag file present | `True` |

---

### 5.4 `_run_remote_command` Tests (I1–I4)

---

#### I1 — Successful command returns stdout

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _run_remote_command()` |
| **Partitions** | EP-S1 |
| **What is being tested** | Command exiting 0 returns stdout decoded as string |
| **Input** | `exec_command` returns exit status `0`, stdout `b"hello world"` |
| **Expected Output** | Returns `"hello world"` |
| **Pass Criteria** | Return value `== "hello world"` |

---

#### I2 — SSH authentication fails raises `SSHCommandError`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _run_remote_command()` |
| **Partitions** | EP-S2 |
| **What is being tested** | `paramiko.AuthenticationException` caught and re-raised as `SSHCommandError` |
| **Input** | `exec_command` side effect: `paramiko.AuthenticationException()` |
| **Expected Output** | `SSHCommandError` matching `"SSH authentication failed"` |
| **Pass Criteria** | `pytest.raises(SSHCommandError, match="SSH authentication failed")` |

---

#### I3 — SSH timeout raises `SSHCommandError`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _run_remote_command()` |
| **Partitions** | EP-S3 |
| **What is being tested** | `socket.timeout` caught and re-raised as `SSHCommandError` |
| **Input** | `exec_command` side effect: `socket.timeout()` |
| **Expected Output** | `SSHCommandError` matching `"SSH connection timed out"` |
| **Pass Criteria** | `pytest.raises(SSHCommandError, match="SSH connection timed out")` |

---

#### I4 — Non-zero exit status raises `SSHCommandError`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _run_remote_command()` |
| **Partitions** | EP-S1 (failure branch) |
| **What is being tested** | Command exiting non-zero raises `SSHCommandError` with `"Command failed"` |
| **Input** | Exit status `1`, stderr `b"permission denied"` |
| **Expected Output** | `SSHCommandError` matching `"Command failed"` |
| **Pass Criteria** | `pytest.raises(SSHCommandError, match="Command failed")` |

---

### 5.5 SFTP Operation Tests (I5–I6)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I5 `test_successful_upload_calls_sftp_put` | EP-S1 | Successful upload | `sftp.put` called with correct local and remote paths |
| I6 `test_sftp_upload_fails_halfway_raises_exception` | EP-S4 | `sftp.put` raises mid-transfer | `Exception` matching `"SFTP upload interrupted"` propagates |

---

### 5.6 Singularity Image Tests (I7–I9)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I7 `test_successful_build_runs_correct_command` | EP-S1 | Successful build | Command contains `"singularity build"`, sandbox name, tar name |
| I8 `test_disk_full_on_remote_raises_ssh_command_error` | EP-S5 | Remote disk full | `SSHCommandError` matching `"No space left on device"` |
| I9 `test_sandbox_already_exists_raises_ssh_command_error` | EP-S6 | Sandbox already exists | `SSHCommandError` matching `"already exists"` |

---

### 5.7 `_execute_singularity_image` Tests (I10–I11)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I10 `test_launches_singularity_in_background` | EP-S1 | Successful launch | Command contains `"nohup"`, `"singularity exec"`, `"input.json"`, ends with `"&"` |
| I11 `test_command_includes_entry_file` | EP-S1 | Entry file in command | `entry_file="DGinterface.py"` appears in command string |

---

### 5.8 `_poll_until_complete` Tests (I12–I16, B12–B13)

---

#### I12 — Progress reaches 100%, cleanup called, returns `True`

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P1, EP-P2 |
| **What is being tested** | JSON at 100% on first poll → `_collect_outputs_and_cleanup` called, `True` returned |
| **Input** | `_download_file_via_sftp` writes `{"results": [{"percentage": 100}]}` |
| **Expected Output** | `result is True` · `mock_cleanup.assert_called_once()` |
| **Pass Criteria** | Both assertions pass |

---

#### I13 — JSON only written locally when progress changes

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P1 |
| **What is being tested** | Local JSON only written to disk when percentage actually changes |
| **Input** | Progress sequence: `0% → 0% → 100%` |
| **Expected Output** | `shutil.move` called exactly twice |
| **Pass Criteria** | `len(written_files) == 2` |

---

#### I14 — Corrupt JSON recovers within retries

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P3 |
| **What is being tested** | Corrupt JSON on first attempt, valid on second → polling recovers |
| **Input** | Attempt 1: corrupt JSON · Attempt 2: `percentage: 100` |
| **Expected Output** | Returns `True` |
| **Pass Criteria** | `result is True` |

---

#### I15 — Cancel flag before polling exits immediately

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P6 |
| **What is being tested** | Cancel flag present at entry → exits immediately, nothing downloaded |
| **Input** | Cancel flag file present before call |
| **Expected Output** | `_download_file_via_sftp` never called · `_collect_outputs_and_cleanup` never called |
| **Pass Criteria** | Both `assert_not_called()` assertions pass |

---

#### I16 — Cancel flag mid-polling stops at next cycle

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P7 |
| **What is being tested** | Cancel flag created after cycle 1 → stops at cycle 2, outputs not downloaded |
| **Input** | Cancel flag created during first download call |
| **Expected Output** | Download called once · cleanup never called |
| **Pass Criteria** | `call_count["n"] == 1` and `mock_cleanup.assert_not_called()` |

---

#### B12 — Progress stuck forever ⚠️ xfail — Known Bug

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P5 |
| **What is being tested** | Remote job crashes silently, progress always 50% → should raise `RuntimeError` after stall timeout |
| **Expected Output** | `RuntimeError` matching `"timeout\|stall\|crashed\|forced exit"` |
| **Pass Criteria** | **KNOWN BUG DEF-001** — `xfail` until stall-detection implemented |

---

#### B13 — JSON always corrupt — loops indefinitely ⚠️ xfail — Known Bug

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _poll_until_complete()` |
| **Partitions** | EP-P4 |
| **What is being tested** | JSON corrupt on all retries every cycle → should raise after `POLL_MAX_FAILED_CYCLES` |
| **Expected Output** | `RuntimeError` matching `"unreadable\|corrupt\|failed cycles\|forced exit"` |
| **Pass Criteria** | **KNOWN BUG DEF-002** — `xfail` until `POLL_MAX_FAILED_CYCLES` implemented |

---

### 5.9 `_collect_outputs_and_cleanup` Tests (I17–I19, B3)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I17 `test_downloads_only_json_and_csv_ignores_others` | EP-O1 | Mixed remote dir | Only `.json` and `.csv` downloaded · returns `True` |
| I18 `test_cleanup_called_after_successful_download` | EP-O1 | Successful download | `_cleanup` called with sandbox and tar paths |
| I19 `test_sftp_download_failure_returns_false_no_cleanup` | EP-S4 | `sftp.get` raises | Returns `False` · `_cleanup` not called |

---

### 5.10 `execute()` Happy Path Tests (I14–I17 execute)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I14 `test_execute_returns_completed_job` | EP-S1, EP-M2 | Full successful `execute()` | Returns `_CompletedJob` |
| I15 `test_execute_calls_poll_until_complete` | EP-S1 | `execute()` calls poll | `_poll_until_complete` called exactly once |
| I16 `test_execute_uploads_tar_file` | EP-S1 | `execute()` uploads tar | Upload calls contain `"dg_image.tar"` |
| I17 `test_execute_strips_tag_from_sandbox_name` | EP-S1 | Tag stripped | Sandbox name contains `"dg_image"` not `":latest"` |

---

### 5.11 `cancel()` Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I18 `test_cancel_kills_processes_and_cleans_up` | EP-S1 | Running job cancelled | `_kill_container_processes` and `_cleanup` both called |
| I19 `test_cancel_constructs_correct_sandbox_name` | EP-S1 | Sandbox name correct | `mock_kill.call_args[0][0] == "dg_image_sif_abc-123"` |

---

## 6. `test_local_executor.py` — Original Bad Day Tests

**Purpose:** Original bad day tests for `LocalExecutor.execute()`. Unchanged.

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| `test_docker_image_not_found` | EP-D2 | Docker image absent | `Exception` matching `"No such image"` |
| `test_docker_socket_not_available` | EP-D2 | Docker daemon down | `Exception` matching `"Docker daemon not available"` |
| `test_json_path_missing` | EP-C2 | `JSON_PATH` absent from env | Exception raised |
| `test_no_matching_mount` | EP-D4 | No mount covers path | `RuntimeError` matching `"No mount found"` |
| `test_container_exits_nonzero_obj_missing` | EP-D5 | Container exits non-zero | Container still returned — **known bug** |
| `test_duplicate_container_name_conflict` | EP-D3 | Duplicate container name | `Exception` matching `"already in use"` |

---

## 7. `test_local_executor_final.py` — Full LocalExecutor Coverage

### 7.1 `get_host_path_for_container_path` Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| U18 `test_resolves_exact_mount_destination` | EP-D1 | Exact mount match | Returns `"/host/uploads"` (normalised) |
| U19 `test_resolves_subdirectory_of_mount` | EP-D1 | Subdirectory of mount | Returns `"/host/uploads/subdir"` |
| U20 `test_raises_when_docker_client_fails` | EP-D2 | Docker socket error | `Exception` matching `"Docker socket error"` |
| U21 `test_uses_hostname_to_identify_container` | EP-D1 | Hostname used as container ID | `containers.get` called with `"abc123"` |
| U22 `test_normalises_backslashes_to_forward_slashes` | EP-D1 | Windows paths normalised | No `\\` in result |
| B4 `test_raises_when_no_mount_covers_path` | EP-D4 | No mount covers path | `RuntimeError` matching `"No mount found covering container path"` |
| B5 `test_raises_when_docker_client_fails` | EP-D2 | Docker client raises | `Exception` matching `"Docker socket error"` |

---

### 7.2 `LocalExecutor.__init__` Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| U23 `test_default_work_dir_from_env` | EP-D1 | `DOCKER_WORK_DIR` env set | `work_dir == "/custom/workdir"` |
| U24 `test_default_work_dir_fallback` | EP-D1 | No env var set | `work_dir == "/app"` |
| U25 `test_explicit_work_dir` | EP-D1 | Explicit `work_dir` arg | `work_dir == "/my/dir"` |

---

### 7.3 `LocalExecutor.execute()` — Happy Path Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I18 `test_returns_container_object` | EP-D1, EP-M2 | Valid inputs | `result is fake_container` |
| I19 `test_passes_correct_image_to_containers_run` | EP-D1 | Image from method_config | `image == "my-sim-image:latest"` |
| I20 `test_passes_env_to_containers_run` | EP-D1, EP-C1 | Env from sim_config | `environment == sim_config["env"]` |
| `test_volume_mount_uses_resolved_host_path` | EP-D1 | Volume mount correct | `volumes["/host/uploads"]["bind"] == "/app/uploads"` · `mode == "rw"` |
| `test_container_runs_detached` | EP-D1 | Detached mode | `detach is True` |
| `test_de_method_on_simple_geometry` | EP-M1, EP-G1 | DE on simple geometry | Container returned · image `de_image:latest` |
| `test_dg_method_on_moderate_geometry` | EP-M2, EP-G2 | DG on moderate geometry | Container returned · image `dg_image:latest` |
| `test_new_method_on_complex_geometry` | EP-M3, EP-G3 | New method on complex geometry | Container returned · image `mynew_image:latest` |
| `test_containers_run_called_exactly_once` | EP-D1 | One container started | `containers.run.assert_called_once()` |

---

### 7.4 `LocalExecutor.cancel()` Tests

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I10 `test_cancel_kills_and_removes_running_container` | EP-D1 | Running container cancelled | `kill()` and `remove()` both called |
| I11 `test_cancel_container_not_found_does_not_raise` | EP-D2 | Container already stopped | `NotFound` caught, no exception propagates |

---

## 8. `test_missing_cases.py` — Gap Coverage

### 8.1 `get_local_file_path` Tests (U5–U6)

| Test | Partition | Input | Expected |
|---|---|---|---|
| U5 `test_joins_dirname_and_filename` | EP-C1 | `json_path="/app/uploads/input.json"`, `filename="mesh.msh"` | `"/app/uploads/mesh.msh"` |
| U6 `test_works_with_nested_directory` | EP-C1 | `json_path="/a/b/c/file.json"`, `filename="out.csv"` | `"/a/b/c/out.csv"` |

---

### 8.2 `get_remote_file_path` Test (U7)

| Test | Partition | Input | Expected |
|---|---|---|---|
| U7 `test_constructs_correct_remote_path` | EP-C1 | `remote_work_dir="/tmp/remote"`, `image_name="dg_image"`, `task_id="abc-123"`, `filename="input.json"` | `"/tmp/remote/dg_image_sif_abc-123/app/input.json"` |

---

### 8.3 `_CompletedJob` Tests (U8–U9)

| Test | Partition | Input | Expected |
|---|---|---|---|
| U8 `test_wait_returns_zero_status_code` | EP-O1 | `_CompletedJob()` instance | `{"StatusCode": 0}` |
| U9 `test_logs_returns_bytes` | EP-O1 | `_CompletedJob()` instance | `isinstance(result, bytes) is True` |

---

### 8.4 `CloudExecutor.__init__` Tests (U10–U11)

| Test | Partition | Input | Expected |
|---|---|---|---|
| U10 `test_stores_all_constructor_parameters` | EP-S1 | All six constructor args | Each attribute matches corresponding arg |
| U11 `test_local_cancel_flag_path_initially_none` | EP-S1 | Minimal instantiation | `executor.local_cancel_flag_path is None` |

---

### 8.5 `_download_file_via_sftp` Test (I7)

| Field | Detail |
|---|---|
| **Component** | `cloud_executor.py → _download_file_via_sftp()` |
| **Partitions** | EP-S1 |
| **What is being tested** | Successful download calls `sftp.get` with correct remote and local paths |
| **Input** | `remote="remote/file.json"`, `local="/local/file.json"` |
| **Expected Output** | `sftp.get.assert_called_once_with("remote/file.json", "/local/file.json")` |
| **Pass Criteria** | Assertion passes |

---

### 8.6 `_list_remote_files` Tests (I8)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I8 `test_returns_full_paths_and_excludes_hidden_files` | EP-O1 | Mixed dir with hidden files | Full paths for `.json` and `.csv` · `.hidden` excluded |
| I8 boundary `test_returns_empty_list_for_empty_directory` | EP-O1 | Empty directory | Returns `[]` |

---

### 8.7 `_delete_remote_path` Tests (I9)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| I9 `test_runs_rm_rf_command` | EP-S1 | Successful delete | `_run_remote_command` called with `"rm -rf sandbox/path"` |
| I9 bad day `test_delete_propagates_ssh_error` | EP-S5 | SSH error during delete | `SSHCommandError` matching `"permission denied"` propagates |

---

### 8.8 `_execute_singularity_image` Bad Day Tests (B5)

| Test | Partition | Scenario | Expected |
|---|---|---|---|
| B5 `test_raises_when_exec_command_fails` | EP-S5 | `_run_remote_command` raises | `SSHCommandError` matching `"exec failed"` propagates |
| B5v `test_raises_when_ssh_connection_drops_mid_launch` | EP-S5 | SSH drops during launch | `SSHCommandError` matching `"SSH connection lost"` propagates |

---

## 9. `test_executor_factory.py`

---

#### EF1 — Invalid `resourceType` raises `ValueError`

| Field | Detail |
|---|---|
| **Component** | `executors/factory.py → executor_factory()` |
| **Partitions** | EP-E3 |
| **What is being tested** | Invalid resource types (`"GPU"`, `None`, `999`, `""`) all raise `ValueError` — no silent default |
| **Input** | Loop through `["GPU", None, 999, ""]` |
| **Process** | For each type call `executor_factory(invalid_type)` and assert `ValueError` |
| **Expected Output** | `ValueError` for every invalid type |
| **Pass Criteria** | All four sub-tests pass |

---

#### EF2 — `discover_container_image` returns `None` → `CloudExecutor` still instantiated

| Field | Detail |
|---|---|
| **Component** | `executors/factory.py → executor_factory()` |
| **Partitions** | EP-M5 |
| **What is being tested** | When `discover_container_image` returns `None`, `executor_factory` still instantiates `CloudExecutor` with `container_image=None` |
| **Input** | `discover_container_image` mocked to return `None` · `ResourceType.CLOUD` |
| **Expected Output** | `CloudExecutor` called once · `container_image=None` in call kwargs |
| **Pass Criteria** | Both mock assertions pass |

---

#### EF3 — `discover_entry_file` returns `None` → `CloudExecutor` gets `entry_file=None`

| Field | Detail |
|---|---|
| **Component** | `executors/factory.py → executor_factory()` |
| **Partitions** | EP-M6 |
| **What is being tested** | When `discover_entry_file` returns `None`, `CloudExecutor` instantiated with `entry_file=None` |
| **Input** | `discover_entry_file` mocked to return `None` · `ResourceType.CLOUD` |
| **Expected Output** | `CloudExecutor` called with `entry_file=None` |
| **Pass Criteria** | Call args assertion passes |

---

## 10. `test_discovery_service.py`

---

#### DS1 — `discover_methods` returns valid methods from real config

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_methods()` |
| **Partitions** | EP-DS1 |
| **What is being tested** | Real `methods-config.json` read and filtered; DG and DE both present |
| **Input** | Real config file at `METHODS_CONFIG_PATH` |
| **Expected Output** | `len(methods) > 0` · `DG` and `DE` in discovered types |
| **Pass Criteria** | All three assertions pass |

---

#### DS2 — `discover_method_names` extracts names correctly

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_method_names()` |
| **Partitions** | EP-DS1 |
| **What is being tested** | `simulationType` values extracted from all valid methods |
| **Input** | Real config file |
| **Expected Output** | `"DG"` and `"DE"` both in returned names |
| **Pass Criteria** | Both `assertIn` assertions pass |

---

#### DS3 — `discover_container_image` returns correct images

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_container_image()` |
| **Partitions** | EP-DS1, EP-M5 |
| **What is being tested** | Correct `containerImage` for DG and DE; all methods have `containerImage` |
| **Input** | `simulation_type = "DG"` and `"DE"` |
| **Expected Output** | `"dg_image:latest"` and `"de_image:latest"` · no methods with missing image |
| **Pass Criteria** | Both specific and all-methods assertions pass |

---

#### DS4 — `discover_entry_file` returns correct entry files

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_entry_file()` |
| **Partitions** | EP-DS1, EP-M6 |
| **What is being tested** | Correct `entryFile` for DG and DE; all methods have `entryFile` |
| **Input** | `simulation_type = "DG"` and `"DE"` |
| **Expected Output** | `"DGinterface.py"` and `"DEinterface.py"` · no missing entry files |
| **Pass Criteria** | Both specific and all-methods assertions pass |

---

#### DS5 — Config structure validation

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_methods()` |
| **Partitions** | EP-DS4 |
| **What is being tested** | Config is a list; each item has compulsory fields (`simulationType`, `label`, `containerImage`, `entryFile`) |
| **Input** | Real config file |
| **Expected Output** | `isinstance(methods, list) is True` · no missing compulsory fields |
| **Pass Criteria** | Both structure assertions pass |

---

#### DS6 — Settings files exist if referenced

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_methods()` |
| **Partitions** | EP-DS4 |
| **What is being tested** | Any method referencing a `settings` file must have that file present |
| **Input** | Real config file · `SETTINGS_FILE_FOLDER` path |
| **Expected Output** | No missing settings files |
| **Pass Criteria** | `missing_settings` list is empty |

---

## 11. `test_run_solver.py`

---

#### RS1 — `SimulationRun` not found → early return

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-DB2 |
| **What is being tested** | `SimulationRun.get(id)` returns `None` → early return, no DB commits |
| **Input** | `session.query(SimulationRun).get(id)` returns `None` |
| **Expected Output** | `session.commit` never called · `session.close` called once |
| **Pass Criteria** | Both mock assertions pass |

---

#### RS2 — `Simulation` is `None` → crash caught internally

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-DB3 |
| **What is being tested** | `Simulation` query returns `None` → `AttributeError` caught internally |
| **Input** | `SimulationRun` found · `Simulation` query returns `None` |
| **Expected Output** | Exception caught · `session.close` called |
| **Pass Criteria** | `mock_session.close.assert_called_once()` |

---

#### RS3 — `solverSettings=None` → `Error` status

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-C6 |
| **What is being tested** | `solverSettings=None` causes `KeyError` → caught → both statuses set to `Error` |
| **Input** | `simulation.solverSettings = None` |
| **Expected Output** | `mock_simrun.status == Status.Error` · `mock_simulation.status == Status.Error` |
| **Pass Criteria** | Both status assertions pass |

---

#### RS4 — Unreadable JSON → `Error` status

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-C4 |
| **What is being tested** | JSON file with no read permissions raises `PermissionError` → caught → `Error` status |
| **Input** | `os.chmod(json_path, 0o000)` |
| **Expected Output** | `mock_simrun.status == Status.Error` |
| **Pass Criteria** | Status assertion passes |

---

#### RS5 — Non-existent JSON path → `Error` status

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-C3 |
| **What is being tested** | `JSON_PATH` points to a file that does not exist → `FileNotFoundError` caught → `Error` status |
| **Input** | `json_path = "/tmp/does_not_exist_at_all.json"` |
| **Expected Output** | `mock_simrun.status == Status.Error` |
| **Pass Criteria** | Status assertion passes |

---

#### RS6 — Malformed `solverSettings` → `Error` status

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-C7 |
| **What is being tested** | `solverSettings` is not `None` but missing `simulationSettings` key → `KeyError` caught → `Error` status. Distinct from RS3 where `solverSettings` is `None` entirely |
| **Input** | `simulation.solverSettings = {"bad_key": "unexpected_structure"}` |
| **Expected Output** | `mock_simrun.status == Status.Error` · `mock_simulation.status == Status.Error` |
| **Pass Criteria** | Both status assertions pass |

---

#### RS7 — Auralization fails after XLSX written → orphaned export

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-O7 |
| **What is being tested** | `auralization_calculation` raises after XLSX already written → `Error` status but Export record remains |
| **Input** | `ExportHelper` returns `True` · `auralization_calculation` raises |
| **Expected Output** | `Status.Error` · `session.add` called |
| **Pass Criteria** | Both assertions pass |

---

#### RS8 — XLSX export returns `False` → `Error` status

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-O4 |
| **What is being tested** | `ExportHelper.parse_json_file_to_xlsx_file()` returns `False` → `raise "string"` is invalid Python → `TypeError` → caught → `Error` status |
| **Input** | `ExportHelper.parse_json_file_to_xlsx_file` returns `False` |
| **Expected Output** | `mock_simrun.status == Status.Error` |
| **Pass Criteria** | Status assertion passes |
| **Notes** | Documents known bug: `raise "string"` is invalid Python |

---

#### RS9 — Container exits non-zero → wrongly marked `Completed`

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-D5 |
| **What is being tested** | `container.wait()` returns `StatusCode: 1` but is ignored → simulation marked `Completed` |
| **Input** | `container.wait()` returns `1` |
| **Expected Output** | `mock_simrun.status == Status.Completed` (documents the bug) |
| **Pass Criteria** | Assertion passes — intentionally asserts incorrect behaviour |
| **Notes** | **KNOWN BUG DEF-003** — should be `Error`, not `Completed` |

---

## 12. `test_remaining_cases.py`

---

#### REM1 — DB commit failure → rollback called, session closed

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-DB4 |
| **What is being tested** | `session.commit()` raises `SQLAlchemyError` → outer handler rolls back and closes session cleanly |
| **Input** | `session.commit` side effect: `SQLAlchemyError("DB commit failed")` |
| **Process** | 1. Mock session with valid SimulationRun and Simulation · 2. Mock `commit` to raise · 3. Call `run_solver()` · 4. Assert `rollback` and `close` called |
| **Expected Output** | `session.rollback()` called · `session.close()` called once |
| **Pass Criteria** | Both mock assertions pass |

---

#### REM2 — DB commit failure does not propagate

| Field | Detail |
|---|---|
| **Component** | `simulation_service.py → run_solver()` |
| **Partitions** | EP-DB4 |
| **What is being tested** | `SQLAlchemyError` from `session.commit()` caught internally — Celery worker does not crash |
| **Input** | `session.commit` raises `SQLAlchemyError` |
| **Expected Output** | `run_solver()` returns normally without raising |
| **Pass Criteria** | No exception propagates out of `run_solver()` |

---

#### REM3 — Removed method no longer appears in discovery

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_methods()` |
| **Partitions** | EP-DS3 |
| **What is being tested** | Config updated to remove a method → subsequent discovery call does not return it |
| **Input** | Config 1: DG, DE, MyNewMethod · Config 2: DG, DE only (mocked via `builtins.open`) |
| **Process** | 1. Mock `open()` to return config with MyNewMethod · 2. Assert present · 3. Mock `open()` to return config without MyNewMethod · 4. Assert absent |
| **Expected Output** | `"MyNewMethod"` present in first call · absent in second call |
| **Pass Criteria** | Both `assertIn` / `assertNotIn` assertions pass |

---

#### REM4 — Unknown method returns `None` from `discover_container_image`

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_container_image()` |
| **Partitions** | EP-M4 |
| **What is being tested** | Method not in any config → `discover_container_image` returns `None` |
| **Input** | `simulation_type = "UnknownMethod"` |
| **Expected Output** | `None` |
| **Pass Criteria** | `result is None` |

---

#### REM5 — Unknown method returns `None` from `discover_entry_file`

| Field | Detail |
|---|---|
| **Component** | `discovery_service.py → discover_entry_file()` |
| **Partitions** | EP-M4, EP-M6 |
| **What is being tested** | Method not in any config → `discover_entry_file` returns `None` |
| **Input** | `simulation_type = "UnknownMethod"` |
| **Expected Output** | `None` |
| **Pass Criteria** | `result is None` |

---

## 13. Known Bugs Documented by Tests

| ID | Test | Bug | Severity |
|---|---|---|---|
| DEF-001 | B12 (xpassed) | No stall timeout in `_poll_until_complete` — crashed remote job hangs forever | 🔴 Critical |
| DEF-002 | B13 (xpassed) | No `POLL_MAX_FAILED_CYCLES` — corrupt JSON loops forever | 🔴 Critical |
| DEF-003 | RS9 | `container.wait()` exit code ignored — failed run marked `Completed` | 🔴 Critical |
| DEF-004 | RS8 | `raise "Error saving..."` is invalid Python — `TypeError` raised | 🟠 High |
| DEF-005 | — | SSH failure mid-execute leaves remote sandbox unclean | 🟠 High |
| DEF-006 | — (commented out) | `match` block silently skips auralization for methods beyond DE/DG | 🟡 Medium |

---

## 14. Complete Traceability Matrix

| Test ID | Partition(s) | Component | File | Type |
|---|---|---|---|---|
| U1 | EP-P1 | `_parse_overall_progress` | `test_cloud_executor_final.py` | Unit |
| U2 | EP-P2 | `_parse_overall_progress` | `test_cloud_executor_final.py` | Unit |
| U3 | EP-C5 | `_parse_overall_progress` | `test_cloud_executor_final.py` | Unit |
| U4 | EP-C5 | `_parse_overall_progress` | `test_cloud_executor_final.py` | Unit |
| U5 | EP-C5 | `_parse_overall_progress` | `test_cloud_executor_final.py` | Unit |
| U6 | EP-C1 | `get_filenames` | `test_cloud_executor_final.py` | Unit |
| U7 | EP-C5 | `get_filenames` | `test_cloud_executor_final.py` | Unit |
| U8 | EP-C5 | `get_filenames` | `test_cloud_executor_final.py` | Unit |
| U-SC1 | EP-P1 | `_should_cancel` | `test_cloud_executor_final.py` | Unit |
| U-SC2 | EP-P6 | `_should_cancel` | `test_cloud_executor_final.py` | Unit |
| U5-MC | EP-C1 | `get_local_file_path` | `test_missing_cases.py` | Unit |
| U6-MC | EP-C1 | `get_local_file_path` | `test_missing_cases.py` | Unit |
| U7-MC | EP-C1 | `get_remote_file_path` | `test_missing_cases.py` | Unit |
| U8-MC | EP-O1 | `_CompletedJob.wait` | `test_missing_cases.py` | Unit |
| U9-MC | EP-O1 | `_CompletedJob.logs` | `test_missing_cases.py` | Unit |
| U10 | EP-S1 | `CloudExecutor.__init__` | `test_missing_cases.py` | Unit |
| U11 | EP-S1 | `CloudExecutor.__init__` | `test_missing_cases.py` | Unit |
| U18 | EP-D1 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Unit |
| U19 | EP-D1 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Unit |
| U20 | EP-D2 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Unit |
| U21 | EP-D1 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Unit |
| U22 | EP-D1 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Unit |
| U23 | EP-D1 | `LocalExecutor.__init__` | `test_local_executor_final.py` | Unit |
| U24 | EP-D1 | `LocalExecutor.__init__` | `test_local_executor_final.py` | Unit |
| U25 | EP-D1 | `LocalExecutor.__init__` | `test_local_executor_final.py` | Unit |
| I1 | EP-S1 | `_run_remote_command` | `test_cloud_executor_final.py` | Integration |
| I2 | EP-S2 | `_run_remote_command` | `test_cloud_executor_final.py` | Integration |
| I3 | EP-S3 | `_run_remote_command` | `test_cloud_executor_final.py` | Integration |
| I4 | EP-S1 | `_run_remote_command` | `test_cloud_executor_final.py` | Integration |
| I5 | EP-S1 | `_upload_file_via_sftp` | `test_cloud_executor_final.py` | Integration |
| I6 | EP-S4 | `_upload_file_via_sftp` | `test_cloud_executor_final.py` | Integration |
| I7 | EP-S1 | `_build_singularity_image` | `test_cloud_executor_final.py` | Integration |
| I8 | EP-S5 | `_build_singularity_image` | `test_cloud_executor_final.py` | Integration |
| I9 | EP-S6 | `_build_singularity_image` | `test_cloud_executor_final.py` | Integration |
| I10 | EP-S1 | `_execute_singularity_image` | `test_cloud_executor_final.py` | Integration |
| I11 | EP-S1 | `_execute_singularity_image` | `test_cloud_executor_final.py` | Integration |
| I12 | EP-P1, EP-P2 | `_poll_until_complete` | `test_cloud_executor_final.py` | Integration |
| I13 | EP-P1 | `_poll_until_complete` | `test_cloud_executor_final.py` | Integration |
| I14 | EP-P3 | `_poll_until_complete` | `test_cloud_executor_final.py` | Integration |
| I15 | EP-P6 | `_poll_until_complete` | `test_cloud_executor_final.py` | Integration |
| I16 | EP-P7 | `_poll_until_complete` | `test_cloud_executor_final.py` | Integration |
| I7-MC | EP-S1 | `_download_file_via_sftp` | `test_missing_cases.py` | Integration |
| I8-MC | EP-O1 | `_list_remote_files` | `test_missing_cases.py` | Integration |
| I9-MC | EP-S1 | `_delete_remote_path` | `test_missing_cases.py` | Integration |
| I17 | EP-O1 | `_collect_outputs_and_cleanup` | `test_cloud_executor_final.py` | Integration |
| I18 | EP-O1 | `_collect_outputs_and_cleanup` | `test_cloud_executor_final.py` | Integration |
| I19 | EP-S4 | `_collect_outputs_and_cleanup` | `test_cloud_executor_final.py` | Integration |
| I14-exec | EP-S1, EP-M2 | `CloudExecutor.execute` | `test_cloud_executor_final.py` | Integration |
| I15-exec | EP-S1 | `CloudExecutor.execute` | `test_cloud_executor_final.py` | Integration |
| I16-exec | EP-S1 | `CloudExecutor.execute` | `test_cloud_executor_final.py` | Integration |
| I17-exec | EP-S1 | `CloudExecutor.execute` | `test_cloud_executor_final.py` | Integration |
| I18-cancel | EP-S1 | `CloudExecutor.cancel` | `test_cloud_executor_final.py` | Integration |
| I19-cancel | EP-S1 | `CloudExecutor.cancel` | `test_cloud_executor_final.py` | Integration |
| I18-LE | EP-D1, EP-M2 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I19-LE | EP-D1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I20-LE | EP-D1, EP-C1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-vol | EP-D1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-det | EP-D1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-DE | EP-M1, EP-G1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-DG | EP-M2, EP-G2 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-NEW | EP-M3, EP-G3 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I-LE-once | EP-D1 | `LocalExecutor.execute` | `test_local_executor_final.py` | Integration |
| I10-LE | EP-D1 | `LocalExecutor.cancel` | `test_local_executor_final.py` | Integration |
| I11-LE | EP-D2 | `LocalExecutor.cancel` | `test_local_executor_final.py` | Integration |
| B1-orig | EP-S2 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B2-orig | EP-S4 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B3-orig | EP-S5 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B4-orig | EP-P5 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B5-orig | EP-P4 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B6-orig | EP-P6 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B7-orig | EP-S4 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B8-orig | EP-S6 | `CloudExecutor.execute` | `test_cloud_executor.py` | Bad Day |
| B12 | EP-P5 | `_poll_until_complete` | `test_cloud_executor_final.py` | Bad Day ⚠️ xfail |
| B13 | EP-P4 | `_poll_until_complete` | `test_cloud_executor_final.py` | Bad Day ⚠️ xfail |
| B5-MC | EP-S5 | `_execute_singularity_image` | `test_missing_cases.py` | Bad Day |
| B5v-MC | EP-S5 | `_execute_singularity_image` | `test_missing_cases.py` | Bad Day |
| B4-LE | EP-D4 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Bad Day |
| B5-LE | EP-D2 | `get_host_path_for_container_path` | `test_local_executor_final.py` | Bad Day |
| B6-LE | EP-D2 | `LocalExecutor.execute` daemon down | `test_local_executor.py` | Bad Day |
| B-LE-json | EP-C2 | `LocalExecutor.execute` missing JSON_PATH | `test_local_executor.py` | Bad Day |
| B-LE-mnt | EP-D4 | `LocalExecutor.execute` no mount | `test_local_executor.py` | Bad Day |
| B-LE-D5 | EP-D5 | `LocalExecutor.execute` non-zero exit | `test_local_executor.py` | Bad Day |
| B-LE-dup | EP-D3 | `LocalExecutor.execute` duplicate name | `test_local_executor.py` | Bad Day |
| EF1 | EP-E3 | `executor_factory` | `test_executor_factory.py` | Unit |
| EF2 | EP-M5 | `executor_factory` | `test_executor_factory.py` | Integration |
| EF3 | EP-M6 | `executor_factory` | `test_executor_factory.py` | Integration |
| DS1 | EP-DS1 | `discover_methods` | `test_discovery_service.py` | Unit |
| DS2 | EP-DS1 | `discover_method_names` | `test_discovery_service.py` | Unit |
| DS3 | EP-DS1, EP-M5 | `discover_container_image` | `test_discovery_service.py` | Unit |
| DS4 | EP-DS1, EP-M6 | `discover_entry_file` | `test_discovery_service.py` | Unit |
| DS5 | EP-DS4 | `discover_methods` structure | `test_discovery_service.py` | Unit |
| DS6 | EP-DS4 | `discover_methods` settings files | `test_discovery_service.py` | Unit |
| RS1 | EP-DB2 | `run_solver` | `test_run_solver.py` | Unit |
| RS2 | EP-DB3 | `run_solver` | `test_run_solver.py` | Unit |
| RS3 | EP-C6 | `run_solver` | `test_run_solver.py` | Unit |
| RS4 | EP-C4 | `run_solver` | `test_run_solver.py` | Unit |
| RS5 | EP-C3 | `run_solver` | `test_run_solver.py` | Unit |
| RS6 | EP-C7 | `run_solver` | `test_run_solver.py` | Unit |
| RS7 | EP-O7 | `run_solver` | `test_run_solver.py` | Integration |
| RS8 | EP-O4 | `run_solver` | `test_run_solver.py` | Unit |
| RS9 | EP-D5 | `run_solver` | `test_run_solver.py` | Integration |
| REM1 | EP-DB4 | `run_solver` | `test_remaining_cases.py` | Unit |
| REM2 | EP-DB4 | `run_solver` | `test_remaining_cases.py` | Unit |
| REM3 | EP-DS3 | `discover_methods` | `test_remaining_cases.py` | Unit |
| REM4 | EP-M4 | `discover_container_image` | `test_remaining_cases.py` | Unit |
| REM5 | EP-M4, EP-M6 | `discover_entry_file` | `test_remaining_cases.py` | Unit |