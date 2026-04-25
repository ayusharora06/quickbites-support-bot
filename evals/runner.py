"""Drive the SupportAgent against scripted scenarios — no simulator.

Customer messages come from `evals/scenarios.yaml` instead of the live
simulator. Each scenario runs the agent for as many turns as the script
provides; the actions emitted across all turns are aggregated and scored
by `rubric.score()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from bot.agent import SupportAgent

from .rubric import score as score_actions

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.yaml"


@dataclass
class ScenarioRun:
    id: str
    name: str
    archetype: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    decision_trace: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    rubric: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def load_scenarios() -> list[dict[str, Any]]:
    with SCENARIOS_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["scenarios"]


def run_scenario(scenario: dict[str, Any]) -> ScenarioRun:
    run = ScenarioRun(
        id=scenario["id"], name=scenario["name"], archetype=scenario["archetype"]
    )
    agent = SupportAgent(session_id=f"eval:{scenario['id']}")
    try:
        for i, customer_msg in enumerate(scenario["customer_turns"], start=1):
            result = agent.respond(customer_msg)
            run.turns.append({
                "turn": i,
                "customer": customer_msg,
                "bot": result.bot_message,
                "actions": result.actions,
                "decision_trace": result.decision_trace,
            })
            run.actions.extend(result.actions)
            run.decision_trace.extend(result.decision_trace)
            # Stop early if the bot already closed the chat.
            if any(a.get("type") == "close" for a in result.actions):
                break
        run.usage = dict(agent.cumulative_usage)
        run.rubric = score_actions(scenario, run.actions)
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"
    return run


def run_all() -> list[ScenarioRun]:
    return [run_scenario(s) for s in load_scenarios()]
