"""Service: build per-method geometry-issue compatibility.

The simulation backend ships a single baseline file
(``example_settings/baseline_geometry_compatibility.json``) that lists every
geometry issue kind and its default compatibility. Each simulation method may
ship its own override file (referenced by ``geometryCompatibility`` in
``methods-config.json``) that overrides only the fields that differ from the
baseline, per issue kind.

This service loads the baseline, loads each method's override, and returns the
fully-merged compatibility for every discovered method.
"""
import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from flask_smorest import abort

from config import DefaultConfig
from app.services.discovery_service import discover_methods

logger = logging.getLogger(__name__)

BASELINE_FILENAME = "baseline_geometry_compatibility.json"

# Worst-case ordering used to aggregate a single `compatible` value per method.
_SEVERITY_RANK = {"compatible": 0, "warning": 1, "incompatible": 2}


def _load_json(path: str) -> Optional[dict]:
    """Load a JSON file, returning ``None`` if it is missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Compatibility file not found: {path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in compatibility file {path}: {e}")
        return None


def _simulation_backend_root() -> str:
    """Root of the simulation backend (the directory holding methods-config.json)."""
    return os.path.dirname(DefaultConfig.METHODS_CONFIG_PATH)


def _load_baseline() -> dict:
    """Load the baseline compatibility file.

    Looks in ``SETTINGS_FILE_FOLDER`` first, then falls back to
    ``<simulation-backend>/example_settings``.
    """
    candidates = [
        os.path.join(DefaultConfig.SETTINGS_FILE_FOLDER, BASELINE_FILENAME),
        os.path.join(_simulation_backend_root(), "example_settings", BASELINE_FILENAME),
    ]
    for path in candidates:
        baseline = _load_json(path)
        if baseline is not None:
            return baseline

    abort(
        500,
        message=(
            f"Baseline geometry compatibility file '{BASELINE_FILENAME}' not found. "
            f"Looked in: {candidates}"
        ),
    )


def _merge_method_override(baseline_issues: dict, override: Optional[dict]) -> dict:
    """Merge a method override on top of the baseline issues, per issue kind.

    Only the fields present in the override replace the baseline fields; every
    other field (and every issue kind not mentioned) is inherited unchanged.
    """
    merged = copy.deepcopy(baseline_issues)
    if not override:
        return merged

    for kind, fields in override.get("issues", {}).items():
        if not isinstance(fields, dict):
            continue
        if kind in merged and isinstance(merged[kind], dict):
            merged[kind].update(fields)
        else:
            merged[kind] = dict(fields)
    return merged


def get_simulation_compatibility() -> Dict[str, Any]:
    """Build the per-method geometry-issue compatibility.

    Returns a payload containing the baseline metadata and, for every
    discovered simulation method, the fully-merged issue compatibility
    (baseline overridden by the method's own override file).
    """
    baseline = _load_baseline()
    baseline_issues = baseline.get("issues", {})
    root = _simulation_backend_root()

    methods: List[Dict[str, Any]] = []
    for cfg in discover_methods():
        sim_type = cfg.get("simulationType")
        rel_path = cfg.get("geometryCompatibility")

        override: Optional[dict] = None
        if rel_path:
            override = _load_json(os.path.join(root, rel_path))

        methods.append(
            {
                "simulationType": sim_type,
                "label": cfg.get("label"),
                "notes": override.get("notes") if override else None,
                "issues": _merge_method_override(baseline_issues, override),
            }
        )

    return {
        "version": baseline.get("version"),
        "compatibilityLevels": baseline.get("compatibilityLevels"),
        "methods": methods,
    }


def _local_path_from_upload_url(file_url: str) -> str:
    """Resolve an uploads file URL to its on-disk path inside UPLOAD_FOLDER.

    Only the basename is used (path traversal in the URL is ignored), so the
    result always stays within ``UPLOAD_FOLDER``.
    """
    filename = os.path.basename(urlparse(file_url).path)
    return os.path.join(DefaultConfig.UPLOAD_FOLDER, filename)


def _read_issue_report(file_url: Optional[str]) -> tuple[set, set]:
    """Read the model report and return ``(report_keys, present_kinds)``.

    The report is keyed by IssueKind enum values (matching the compatibility
    tables). ``report_keys`` is every key present in the report (even when its
    list is empty); ``present_kinds`` is the subset whose list is non-empty.
    Returns two empty sets when the report is missing or unreadable.
    """
    if not file_url:
        return set(), set()

    report = _load_json(_local_path_from_upload_url(file_url))
    if not isinstance(report, dict):
        return set(), set()

    report_keys = {
        kind for kind, entries in report.items() if isinstance(entries, list)
    }
    present_kinds = {
        kind
        for kind, entries in report.items()
        if isinstance(entries, list) and entries
    }
    return report_keys, present_kinds


def _method_result(
    method: Dict[str, Any], report_keys: set, present_kinds: set
) -> Dict[str, Any]:
    """Resolve one method's compatibility against the model report.

    ``compatible`` is the worst-case compatibility among the issue kinds that
    are present (non-empty) in the report. It is ``"unknown"`` when the method
    declares a kind the report has no information about (the kind is not a key
    in the report at all), otherwise ``"compatible"`` when nothing is present.
    """
    issues_out: List[Dict[str, Any]] = []
    worst: Optional[str] = None
    has_unknown = False

    for kind, meta in (method.get("issues") or {}).items():
        compatibility = meta.get("compatibility")
        present = kind in present_kinds

        if kind not in report_keys:
            has_unknown = True

        issues_out.append(
            {
                "kind": kind,
                "label": meta.get("label"),
                "compatibility": compatibility,
                "present": present,
            }
        )

        if present and compatibility in _SEVERITY_RANK:
            if worst is None or _SEVERITY_RANK[compatibility] > _SEVERITY_RANK[worst]:
                worst = compatibility

    if worst is not None:
        compatible = worst
    elif has_unknown:
        compatible = "unknown"
    else:
        compatible = "compatible"

    return {
        "simulationType": method.get("simulationType"),
        "label": method.get("label"),
        "notes": method.get("notes"),
        "compatible": compatible,
        "issues": issues_out,
    }


def get_model_simulation_compatibility(model_id: int) -> Dict[str, Any]:
    """Build per-method compatibility for a specific model's repaired geometry.

    Loads the model's ``AfterRepair`` issue report and, for every simulation
    method, resolves how its configured compatibility applies to the issues
    that remain in that model.
    """
    from app.models import Model, ModelIssue
    from app.types import DetectionStage

    model = Model.query.filter_by(id=model_id).first()
    if not model:
        abort(404, message=f"Model {model_id} does not exist")

    model_issue = (
        ModelIssue.query.filter_by(
            modelId=model_id, detectionStage=DetectionStage.AfterRepair
        )
        .order_by(ModelIssue.id.desc())
        .first()
    )
    if not model_issue:
        abort(404, message=f"No AfterRepair issue report found for model {model_id}")

    report_keys, present_kinds = _read_issue_report(model_issue.fileUrl)

    base = get_simulation_compatibility()
    methods = [
        _method_result(m, report_keys, present_kinds)
        for m in base.get("methods", [])
    ]

    return {
        "version": base.get("version"),
        "compatibilityLevels": base.get("compatibilityLevels"),
        "modelId": model_id,
        "detectionStage": DetectionStage.AfterRepair.value,
        "methods": methods,
    }
