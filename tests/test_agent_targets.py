import asyncio

from pydantic import ValidationError

from agents.planner import planner_node
from app.api.agent_runs import RunRequest


def test_manual_targets_bypass_fallback_planner():
    target = {"source": "clinicaltrials", "query": "pembrolizumab"}
    result = asyncio.run(planner_node({"run_id": "demo", "targets": [target]}))
    assert result["targets"] == [target]
    assert result["status"] == "researching"


def test_run_targets_are_bounded_and_validate_source():
    request = RunRequest.model_validate(
        {"targets": [{"query": "test", "source": "ema"}]}
    )
    assert request.targets[0].source == "ema"
    try:
        RunRequest.model_validate({"targets": [{"query": "test", "source": "unknown"}]})
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown source was accepted")
