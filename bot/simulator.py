"""Simulator HTTP client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import CANDIDATE_TOKEN, SIMULATOR_BASE_URL


@dataclass
class StartResponse:
    session_id: str
    mode: str
    scenario_id: int
    customer_message: str
    max_turns: int


@dataclass
class ReplyResponse:
    customer_message: str | None
    done: bool
    close_reason: str | None
    score: dict[str, Any] | None
    turns_remaining: int


class SimulatorClient:
    def __init__(
        self,
        base_url: str = SIMULATOR_BASE_URL,
        token: str = CANDIDATE_TOKEN,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Candidate-Token": token, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SimulatorClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def start(self, mode: str = "dev", scenario_id: int | None = None) -> StartResponse:
        body: dict[str, Any] = {"mode": mode}
        if scenario_id is not None:
            body["scenario_id"] = scenario_id
        r = self._client.post("/v1/session/start", json=body)
        r.raise_for_status()
        d = r.json()
        return StartResponse(
            session_id=d["session_id"],
            mode=d["mode"],
            scenario_id=d["scenario_id"],
            customer_message=d["customer_message"],
            max_turns=d["max_turns"],
        )

    def reply(
        self,
        session_id: str,
        bot_message: str,
        actions: list[dict[str, Any]] | None = None,
    ) -> ReplyResponse:
        body = {"bot_message": bot_message, "actions": actions or []}
        r = self._client.post(f"/v1/session/{session_id}/reply", json=body)
        r.raise_for_status()
        d = r.json()
        return ReplyResponse(
            customer_message=d.get("customer_message"),
            done=d.get("done", False),
            close_reason=d.get("close_reason"),
            score=d.get("score"),
            turns_remaining=d.get("turns_remaining", 0),
        )

    def transcript(self, session_id: str) -> dict[str, Any]:
        r = self._client.get(f"/v1/session/{session_id}/transcript")
        r.raise_for_status()
        return r.json()

    def summary(self) -> dict[str, Any]:
        r = self._client.get("/v1/candidate/summary")
        r.raise_for_status()
        return r.json()
