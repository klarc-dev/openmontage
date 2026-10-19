"""The autonomous checkpoint policy: unattended runs pass gates honestly.

Batch production runs with nobody available to approve. Before this policy the
only way through a gated stage was human_approved=True, which forces an agent
to either stop every run or claim an approval that never happened. The
autonomous policy lets a gated stage complete on an automated review record
(reviewer, timestamp, verdict, evidence), stored separately from
human_approved so the audit trail stays truthful.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from tests.contracts.test_phase0_contracts import sample_artifact

from lib.checkpoint import CheckpointValidationError, init_project, write_checkpoint, read_checkpoint

PIPELINE = "framework-smoke"


def _approval(**overrides):
    record = {
        "reviewer": "automated-review",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": "pass",
        "evidence_paths": ["reviews/research.json"],
    }
    record.update(overrides)
    return record


def _script() -> dict:
    return {
        "version": "1.0", "title": "Smoke", "total_duration_seconds": 1,
        "sections": [{"id": "s1", "text": "One second.", "start_seconds": 0, "end_seconds": 1}],
    }


@pytest.fixture
def project(tmp_path):
    init_project("run", title="Run", pipeline_type=PIPELINE, pipeline_dir=tmp_path)
    return tmp_path


def _write_research(project, **kwargs):
    return write_checkpoint(
        project, "run", "research", "completed",
        {"research_brief": sample_artifact("research_brief")},
        pipeline_type=PIPELINE, **kwargs,
    )


def test_gated_stage_completes_on_automated_approval(project) -> None:
    _write_research(project, checkpoint_policy="autonomous", automated_approval=_approval())
    saved = read_checkpoint(project, "run", "research")
    assert saved["status"] == "completed"
    assert saved["human_approved"] is False, "an automated pass must never claim a human approval"
    assert saved["automated_approval"]["verdict"] == "pass"


def test_later_stage_accepts_an_automatically_approved_predecessor(project) -> None:
    _write_research(project, checkpoint_policy="autonomous", automated_approval=_approval())
    write_checkpoint(
        project, "run", "script", "completed", {"script": _script()},
        pipeline_type=PIPELINE, checkpoint_policy="autonomous",
        automated_approval=_approval(evidence_paths=["reviews/script.json"]),
    )
    assert read_checkpoint(project, "run", "script")["status"] == "completed"


def test_autonomous_without_a_record_still_blocks(project) -> None:
    with pytest.raises(CheckpointValidationError, match="GATE VIOLATION"):
        _write_research(project, checkpoint_policy="autonomous")


def test_automated_approval_needs_evidence(project) -> None:
    with pytest.raises(CheckpointValidationError):
        _write_research(project, checkpoint_policy="autonomous", automated_approval=_approval(evidence_paths=[]))


def test_automated_approval_is_refused_outside_the_autonomous_policy(project) -> None:
    with pytest.raises(CheckpointValidationError, match="only valid under"):
        _write_research(project, checkpoint_policy="guided", automated_approval=_approval())


def test_failing_review_cannot_complete_a_gate(project) -> None:
    with pytest.raises(CheckpointValidationError):
        _write_research(project, checkpoint_policy="autonomous", automated_approval=_approval(verdict="fail"))


def test_final_review_schema_accepts_runtime_spotcheck_evidence() -> None:
    import json
    from pathlib import Path

    import jsonschema

    schema = json.loads(Path("schemas/artifacts/final_review.schema.json").read_text(encoding="utf-8"))
    spotcheck = schema["properties"]["checks"]["properties"]["visual_spotcheck"]
    jsonschema.validate(
        {
            "frames_sampled": 4,
            "frame_paths": ["f0.png", "f1.png", "f2.png", "f3.png"],
            "full_size_evidence": [{"scene_id": None, "timestamp_seconds": 1.0, "frame_path": "f.png",
                                    "inspected_full_size": False, "review_notes": ""}],
            "blocking_composition_defects": [],
        },
        spotcheck,
    )
