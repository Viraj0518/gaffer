"""Agent layer tests — scripted models, no API keys, no network."""

import json

from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gaffer.agent import CoachDeps, build_agent

EXPECTED_TOOLS = {
    "list_matches",
    "get_match",
    "possession_stats",
    "shot_stats",
    "passing_stats",
    "defensive_stats",
    "player_match_stats",
    "team_form",
}


def test_all_tools_registered(byo_source):
    seen: set[str] = set()

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.update(tool.name for tool in info.function_tools)
        return ModelResponse(parts=[TextPart("done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(model_fn)):
        result = agent.run_sync("hello", deps=CoachDeps(source=byo_source))
    assert result.output == "done"
    assert seen == EXPECTED_TOOLS


def test_tool_result_flows_back_to_model(byo_source):
    """Scripted run: model calls shot_stats, reads the real computed numbers."""

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="shot_stats", args={"match_id": 1001})]
            )
        report = json.loads(returns[0].model_response_str())
        rovers = next(t for t in report["teams"] if t["team"] == "Rovers")
        return ModelResponse(parts=[TextPart(f"Rovers scored {rovers['goals']}")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(model_fn)):
        result = agent.run_sync("How many did Rovers score?", deps=CoachDeps(source=byo_source))
    assert result.output == "Rovers scored 2"


def test_unknown_player_triggers_model_retry(byo_source):
    """A bad player name must come back as a retry prompt, not an exception."""
    turns = {"count": 0}

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        turns["count"] += 1
        if turns["count"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="player_match_stats",
                        args={"match_id": 1001, "player": "Zlatan"},
                    )
                ]
            )
        retries = [p for p in messages[-1].parts if isinstance(p, RetryPromptPart)]
        assert retries, "expected a retry prompt for the unknown player"
        return ModelResponse(parts=[TextPart("recovered")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(model_fn)):
        result = agent.run_sync("How did Zlatan play?", deps=CoachDeps(source=byo_source))
    assert result.output == "recovered"


def test_fuzzy_player_resolution(byo_source):
    """Lowercase partial name resolves to the canonical player."""

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="player_match_stats",
                        args={"match_id": 1001, "player": "bob"},
                    )
                ]
            )
        report = json.loads(returns[0].model_response_str())
        return ModelResponse(parts=[TextPart(report["player"])])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(model_fn)):
        result = agent.run_sync("bob?", deps=CoachDeps(source=byo_source))
    assert result.output == "Bob"


def test_on_tool_hook_fires(byo_source):
    calls: list[tuple[str, str]] = []

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=[ToolCallPart(tool_name="list_matches", args={})])
        return ModelResponse(parts=[TextPart("ok")])

    deps = CoachDeps(source=byo_source, on_tool=lambda tool, detail: calls.append((tool, detail)))
    agent = build_agent("test")
    with agent.override(model=FunctionModel(model_fn)):
        agent.run_sync("list", deps=deps)
    assert calls == [("list_matches", "all")]
