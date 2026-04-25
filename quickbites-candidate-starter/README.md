# Candidate starter

Welcome. Everything you need is here or in `docs/`.

## Files

- `app.db`            — SQLite snapshot of the business (tables described in
                        `schema.md`).
- `schema.md`         — human-readable documentation of every table.
- `sample_queries.sql`— example queries you can run with
                        `sqlite3 app.db < sample_queries.sql`.
- `policy_and_faq.md` — unstructured company policy + FAQ. You will probably
                        want the bot to consult this.
- `.env.example`      — example environment variables.
- `examples/call_simulator.sh` — a minimal bash/curl script that opens a
                        session and does one reply, so you can confirm the
                        simulator is reachable before writing any code.

## Recommended first 30 minutes

1. Read `docs/ASSIGNMENT.md`.
2. Read `schema.md`. Open `app.db` in a SQLite GUI or via `sqlite3` and
   poke around.
3. Run `examples/call_simulator.sh` against the dev mode of the simulator.
4. Read `docs/SIMULATOR_API.md` end-to-end.
5. Only then start sketching the architecture.

## Stack

Pick whatever you're fastest in. We won't execute your code — you host it.

## What's in `app.db`

Roughly:

- ~50 customers, 20 restaurants, 30 riders
- ~680 delivered/cancelled orders with items
- ~220 complaints, ~120 refunds, ~270 reviews, ~90 rider incidents

The data is deliberately mixed: some customers are model citizens, some are
mixed, a handful are clearly abusing the system. Some restaurants and riders
are great, some are terrible. Your bot needs to tell them apart.

Good luck.
