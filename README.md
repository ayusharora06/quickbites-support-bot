# QuickBites Support Bot

A GenAI customer-support bot for QuickBites (Indian food-delivery). Talks to
customers in plain English, looks up the relevant order/customer/restaurant/rider
history, consults the internal policy, and either resolves the ticket itself
(refund, complaint, abuse flag, escalation) or hands off to a human.

## Architecture (one screen)

```
                       +------------------+
   simulator <-------> |   bot/server.py  |   FastAPI (hosting + dev driver)
   (live customer)     +---------+--------+
                                 |
                       +---------v--------+
                       |   bot/agent.py   |   Claude tool-use loop
                       +---------+--------+
                                 |
              +------------------+----------------------+
              |                                          |
       +------v-------+                          +-------v-------+
       |  bot/data.py |  read-only SQLite        | bot/policy.py |
       |  (lookups)   |  + abuse heuristics      | (FAQ search)  |
       +------+-------+                          +-------+-------+
              |                                          |
        quickbites-candidate-starter/app.db   quickbites-.../policy_and_faq.md
```

The LLM does the *judgement*: which tools to call, how to interpret the
signals, what to say. Everything else (data access, action validation, refund
cap enforcement, simulator wire format) is deterministic Python.

## What's in `bot/`

| file | role |
|---|---|
| `config.py` | env + paths |
| `data.py` | SQL lookups; pre-computes complaint rate, recent refunds, account age, verified vs unverified incident counts, yellow-flag list |
| `policy.py` | loads `policy_and_faq.md`; section-level keyword search |
| `tools.py` | tool schemas (lookup + 5 action tools + `reply`); action validation (refund total ≤ order total, target_type whitelist, etc.) |
| `agent.py` | Claude tool-use loop. System prompt embeds the full policy verbatim. Loops up to 8 iterations per customer turn or until the model calls `reply`. |
| `simulator.py` | thin httpx client for `/v1/session/start`, `/reply`, `/transcript`, `/v1/candidate/summary` |
| `runner.py` | end-to-end CLI driver |
| `server.py` | FastAPI: `/healthz`, `/chat`, `/chat/{id}`, `/run-dev` |

## Setup

```bash
# 1. create env (conda or venv)
conda create -n quickbites python=3.11 -y
conda activate quickbites

# 2. install
pip install -r bot/requirements.txt

# 3. fill in .env at the repo root
#    ANTHROPIC_API_KEY=sk-ant-...
#    SIMULATOR_BASE_URL=https://simulator-75lk3meynq-el.a.run.app
#    CANDIDATE_TOKEN=walnut-quilt-broom-camera
```

## Run

### One dev rehearsal scenario (single command)

```bash
python -m bot.runner dev --scenario 101
```

### All 5 rehearsal scenarios

```bash
python -m bot.runner dev --all
```

### Full graded prod run (22 scenarios)

```bash
python -m bot.runner prod
```

### See current score

```bash
python -m bot.runner summary
```

### Hosting the bot (for reviewers)

```bash
uvicorn bot.server:app --host 0.0.0.0 --port 8000
```

Then `POST /chat` with `{"customer_message": "..."}` returns
`{"conversation_id", "bot_message", "actions"}`. Continue a conversation by
posting to `/chat/{conversation_id}`.

### Offline eval suite (no simulator needed)

```bash
python -m evals
```

Runs 10 hand-built scenarios (credible refund, abuse pattern, prompt
injection, FAQ shortcuts, ambiguous escalation, …) against the agent
locally. Prints a scoreboard and writes `evals/report.md` with per-scenario
actions, rubric breakdown, and token usage. Score ≥80% = exit 0.

## Architecture details

### ReAct state machine

Each `respond()` call walks named phases (PERCEIVE → THINK → DISPATCH →
{OBSERVE | VALIDATE | RESPOND} → FEEDBACK → loop or FINALIZE). Each phase
emits a structured event into the turn's `decision_trace` and into
`transcripts/events.log` (PII-redacted JSONL).

### Prompt caching

The system prompt + policy doc (~2K tokens) and the tool definitions
(~1.2K tokens) are marked with `cache_control: ephemeral`. After turn 1,
each Claude call reads ~3.2K tokens from cache instead of re-billing them
— typically 60–80% cache-hit ratio on the visible per-session input.

### Action validation + idempotency

Every action goes through `bot/tools.py:validate_action()` (refund total
≤ order total, target_type whitelist, etc.) before it leaves the agent.
Each action gets an internal `idempotency_key` (e.g. `refund:261:200:wallet_credit`);
duplicate keys within a session are dropped, so a model retry can't
double-refund.

### Decision-trace transcripts

Each session writes `transcripts/{ts}_{mode}_{scenario}_{sid}.json` with
per-turn `decision_trace` (which lookups, what summary, which actions,
what was rejected). Pair with `transcripts/events.log` for the per-event
JSONL log.

## Design notes

See `DESIGN.md` for the full writeup: policy choices, abuse handling,
prompt-injection resistance, evaluation approach, limitations.
