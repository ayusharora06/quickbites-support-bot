# Simulator API

Base URL: *(provided separately for each candidate)*

Auth: `X-Candidate-Token: <your-token>` header.
 - **dev** mode: token optional (unless our deployment says otherwise).
 - **prod** mode: token required.

All requests and responses are JSON. Timestamps are ISO‑8601.

---

## `POST /v1/session/start`

Open a new chat session. Returns the customer's opening complaint.

### Request

```json
{
  "mode": "dev",                // "dev" | "prod"
  "scenario_id": 101            // optional; dev only; one of the rehearsal
                                // scenario ids listed below. Omit to get a
                                // random rehearsal scenario.
}
```

### Response

```json
{
  "session_id": "e7…",
  "mode": "dev",
  "scenario_id": 103,
  "customer_message": "Half my order is missing…",
  "max_turns": 8
}
```

Only the five fields above are returned — by design. dev mode is for
integrating your bot with the wire protocol and getting a feel for the
conversation, not for previewing the graded scenarios.

### dev mode behaviour

- Picks from a **rehearsal pool** of scenarios (ids `101`–`105`). These are
  NOT the graded scenarios.
- Unlimited sessions, unscored, no rate limit.
- Fetchable transcripts at `GET /v1/session/{id}/transcript` for your own
  debugging.
- `scenario_id` must be one of the rehearsal ids; any other value returns
  `404`.

### prod mode behaviour

- `scenario_id` is ignored; the simulator picks the next unseen scenario for
  your token from the 22-scenario graded set.
- Once all scenarios have been closed for your token, returns `409`.
- Total prod sessions per token are rate-limited (default: 44, 2× the
  scenario count). Use dev for iteration; only go to prod when you're ready.

---

## `POST /v1/session/{session_id}/reply`

Send the bot's reply for this turn and (optionally) the actions the bot
decided to take. Returns the customer's next message or ends the session.

### Request

```json
{
  "bot_message": "I'm sorry about that. I've issued a ₹200 wallet credit.",
  "actions": [
    { "type": "issue_refund", "order_id": 40, "amount_inr": 200, "method": "wallet_credit" },
    { "type": "file_complaint", "order_id": 40, "target_type": "restaurant" }
  ]
}
```

### Action types

| `type` | Required fields | Notes |
|---|---|---|
| `issue_refund` | `order_id`, `amount_inr`, `method` (`cash`\|`wallet_credit`) | Multiple allowed; amounts sum. |
| `file_complaint` | `order_id`, `target_type` (`restaurant`\|`rider`\|`app`) | |
| `escalate_to_human` | `reason` | Use when bot can't / shouldn't resolve. |
| `flag_abuse` | `reason` | Use when you believe the customer is abusing. |
| `close` | `outcome_summary` | Bot closing the chat. Ends the session. |

Actions are graded; prose is not (though prose affects the customer's next
reply). Emit each action at the turn you took it.

### Response

```json
{
  "customer_message": "Okay, thanks.",   // null if done
  "done": false,
  "close_reason": null,                  // "bot_closed" | "customer_closed" | "turn_cap" when done
  "score": null,                         // prod only; populated when done
  "turns_remaining": 6
}
```

Session ends when:

- The bot emits a `close` action.
- The simulated customer emits a line starting with `CLOSE:` (e.g. the
  customer has accepted a resolution, a refusal, or a human escalation).
- Turn cap is reached (max_turns × 2 messages).

---

## `GET /v1/session/{session_id}/transcript` *(dev only)*

Returns the full message + action log. Useful for debugging your bot's own
behaviour. Forbidden in prod mode.

---

## `GET /v1/candidate/summary`

Returns your aggregate score across all completed prod scenarios. Submit
this with your final writeup.

```json
{
  "scenarios_completed": 22,
  "scenarios_total": 22,
  "best_score_per_scenario": { "1": {…}, "2": {…}, … },
  "aggregate_score": 1820,
  "aggregate_max": 2200
}
```

---

## `GET /healthz`

Liveness probe.

---

## Conventions

- Money is always integer INR (no decimals).
- Order/customer/rider/restaurant ids match `app.db`.
- The customer's profile is never exposed via the API — look it up in
  `app.db` using the `order_id` from the opening message if needed.
  (Hint: the customer will tell you their order id when asked.)
