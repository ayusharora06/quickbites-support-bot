"""Run all eval scenarios, print a scoreboard, write evals/report.md."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .runner import run_all

REPORT_PATH = Path(__file__).resolve().parent / "report.md"


def main() -> int:
    runs = run_all()

    # ----- terminal scoreboard ----------------------------------------------
    print(f"\n{'='*78}")
    print(f"{'SCENARIO':<28} {'ARCHETYPE':<26} {'SCORE':>10}")
    print("=" * 78)
    grand = 0
    grand_max = 0
    for r in runs:
        if r.error:
            print(f"{r.id:<28} {r.archetype:<26} {'ERROR':>10}  ← {r.error}")
            continue
        s = r.rubric["total"]
        m = r.rubric["max"]
        grand += s
        grand_max += m
        print(f"{r.id:<28} {r.archetype:<26} {s:>4}/{m:<4}")
    print("-" * 78)
    if grand_max:
        pct = 100 * grand / grand_max
        print(f"{'TOTAL':<28} {'':26} {grand:>4}/{grand_max:<4}   ({pct:.1f}%)")
    print()

    # ----- markdown report --------------------------------------------------
    lines: list[str] = []
    lines.append("# QuickBites bot — offline eval report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    if grand_max:
        lines.append(f"**Aggregate: {grand}/{grand_max} ({100*grand/grand_max:.1f}%)**")
    lines.append("")
    lines.append("| Scenario | Archetype | Score | Refund | Complaint | Abuse | Escalate |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in runs:
        if r.error:
            lines.append(f"| `{r.id}` | {r.archetype} | **ERROR** | — | — | — | — |")
            continue
        c = r.rubric["criteria"]
        rc = c["refund_correctness"]["points_earned"]
        ra = c["refund_amount"]["points_earned"]
        ch = c["complaint_handling"]["points_earned"]
        ab = c["abuse_handling"]["points_earned"]
        es = c["escalation_correctness"]["points_earned"]
        lines.append(
            f"| `{r.id}` | {r.archetype} | **{r.rubric['total']}/100** "
            f"| {rc+ra}/50 | {ch}/15 | {ab}/15 | {es}/10 |"
        )

    lines.append("")
    lines.append("## Per-scenario detail")
    for r in runs:
        lines.append("")
        lines.append(f"### `{r.id}` — {r.name}")
        lines.append(f"*Archetype:* `{r.archetype}`")
        if r.error:
            lines.append(f"\n**ERROR:** `{r.error}`")
            continue
        lines.append("")
        lines.append("**Actions taken:**")
        if not r.actions:
            lines.append("- (none)")
        else:
            for a in r.actions:
                lines.append(f"- `{json.dumps(a, default=str)}`")
        lines.append("")
        lines.append("**Rubric:**")
        for crit, info in r.rubric["criteria"].items():
            lines.append(
                f"- {crit}: {info['points_earned']}/{info['points_max']} — {info['notes']}"
            )
        u = r.usage
        if u:
            lines.append("")
            lines.append(
                f"**Usage:** {u.get('api_calls', 0)} calls, "
                f"in={u.get('input_tokens', 0)} out={u.get('output_tokens', 0)} "
                f"cache_r={u.get('cache_read_input_tokens', 0)} "
                f"cache_w={u.get('cache_creation_input_tokens', 0)}"
            )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"report → {REPORT_PATH}")
    return 0 if grand_max and (grand / grand_max) >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
