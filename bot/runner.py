"""End-to-end session driver.

Usage:
    python -m bot.runner dev                  # one random rehearsal scenario
    python -m bot.runner dev --scenario 103
    python -m bot.runner dev --all            # all 5 rehearsal scenarios
    python -m bot.runner prod --count 22      # full graded run
    python -m bot.runner summary              # show /v1/candidate/summary
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import SYSTEM_PROMPT_HASH, SupportAgent
from .simulator import SimulatorClient

TRANSCRIPT_DIR = Path(__file__).resolve().parent.parent / "transcripts"
TRANSCRIPT_DIR.mkdir(exist_ok=True)

REHEARSAL_IDS = [101, 102, 103, 104, 105]


@dataclass
class SessionLog:
    session_id: str
    scenario_id: int
    mode: str
    system_prompt_hash: str = SYSTEM_PROMPT_HASH
    turns: list[dict[str, Any]] = field(default_factory=list)
    close_reason: str | None = None
    score: dict[str, Any] | None = None
    total_usage: dict[str, int] = field(default_factory=dict)


def _print_turn(role: str, text: str) -> None:
    prefix = {"customer": "👤 CUSTOMER", "bot": "🤖 BOT", "actions": "⚙️  ACTIONS"}.get(
        role, role
    )
    print(f"\n{prefix}: {text}")


def run_session(
    sim: SimulatorClient, mode: str, scenario_id: int | None = None
) -> SessionLog:
    start = sim.start(mode=mode, scenario_id=scenario_id)
    log = SessionLog(session_id=start.session_id, scenario_id=start.scenario_id, mode=mode)
    print(f"\n{'='*70}\nSESSION {start.session_id}  scenario={start.scenario_id}  mode={mode}  max_turns={start.max_turns}\n{'='*70}")
    _print_turn("customer", start.customer_message)

    agent = SupportAgent(session_id=start.session_id)
    customer_msg = start.customer_message
    turn_idx = 0

    while True:
        turn_idx += 1
        try:
            result = agent.respond(customer_msg)
        except Exception as e:
            print(f"\n!! agent error: {e}")
            sim_resp = sim.reply(
                start.session_id,
                "Sorry, I'm hitting an issue on my end. Let me get a human teammate to help.",
                [{"type": "escalate_to_human", "reason": f"agent exception: {e}"}],
            )
            log.turns.append({
                "turn": turn_idx,
                "customer": customer_msg,
                "bot": "(agent error)",
                "actions": [{"type": "escalate_to_human", "reason": str(e)}],
            })
            log.close_reason = sim_resp.close_reason or "agent_error"
            log.score = sim_resp.score
            log.total_usage = dict(agent.cumulative_usage)
            break

        _print_turn("bot", result.bot_message)
        if result.actions:
            _print_turn("actions", json.dumps(result.actions, default=str))
        u = result.usage
        if u:
            print(
                f"   tokens: in={u.get('input_tokens', 0)} "
                f"out={u.get('output_tokens', 0)} "
                f"cache_r={u.get('cache_read_input_tokens', 0)} "
                f"cache_w={u.get('cache_creation_input_tokens', 0)} "
                f"calls={u.get('api_calls', 0)}"
            )

        sim_resp = sim.reply(start.session_id, result.bot_message, result.actions)

        log.turns.append({
            "turn": turn_idx,
            "customer": customer_msg,
            "bot": result.bot_message,
            "actions": result.actions,
            "tool_trace": result.tool_trace,
            "decision_trace": result.decision_trace,
            "turns_remaining": sim_resp.turns_remaining,
            "usage": result.usage,
        })

        if sim_resp.done:
            log.close_reason = sim_resp.close_reason
            log.score = sim_resp.score
            log.total_usage = dict(agent.cumulative_usage)
            print(f"\n--- session done: close_reason={sim_resp.close_reason} ---")
            if sim_resp.score is not None:
                print(f"score: {json.dumps(sim_resp.score, indent=2)}")
            tu = log.total_usage
            cr = tu.get("cache_read_input_tokens", 0)
            cw = tu.get("cache_creation_input_tokens", 0)
            inp = tu.get("input_tokens", 0)
            cache_total = cr + cw
            denom = cache_total + inp
            cache_ratio = (cr / denom) if denom else 0.0
            print(
                f"session usage: {tu.get('api_calls', 0)} calls | "
                f"in={inp} out={tu.get('output_tokens', 0)} "
                f"cache_r={cr} cache_w={cw} | "
                f"cache_hit_ratio={cache_ratio:.0%}"
            )
            break

        customer_msg = sim_resp.customer_message or ""
        _print_turn("customer", customer_msg)

    out = TRANSCRIPT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{mode}_s{log.scenario_id}_{log.session_id[:8]}.json"
    out.write_text(json.dumps(log.__dict__, indent=2, default=str))
    print(f"\ntranscript → {out}")
    return log


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dev")
    d.add_argument("--scenario", type=int)
    d.add_argument("--all", action="store_true", help="run all 5 rehearsal scenarios")

    pr = sub.add_parser("prod")
    pr.add_argument("--count", type=int, default=22, help="how many prod scenarios to run")

    sub.add_parser("summary")

    args = p.parse_args()

    if args.cmd == "summary":
        with SimulatorClient() as sim:
            print(json.dumps(sim.summary(), indent=2))
        return 0

    with SimulatorClient() as sim:
        if args.cmd == "dev":
            if args.all:
                for sid in REHEARSAL_IDS:
                    run_session(sim, "dev", sid)
            else:
                run_session(sim, "dev", args.scenario)
        elif args.cmd == "prod":
            for i in range(args.count):
                print(f"\n###### PROD RUN {i+1}/{args.count} ######")
                try:
                    run_session(sim, "prod", None)
                except Exception as e:
                    print(f"!! prod session failed: {e}")
                    if "409" in str(e):
                        print("All scenarios completed.")
                        break
            print("\n=== final summary ===")
            print(json.dumps(sim.summary(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
