"""FastAPI hosting wrapper.

Endpoints:
- GET  /healthz                — liveness
- POST /chat                   — stateless: { customer_message } → bot reply + actions
                                 Useful for reviewers poking the bot directly.
- POST /chat/{conversation_id} — stateful: agent state held in-process per id.
- POST /run-dev                — convenience: run one rehearsal scenario end-to-end
                                 against the live simulator. body: { scenario_id? }
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import SupportAgent
from .runner import run_session
from .simulator import SimulatorClient

app = FastAPI(title="QuickBites Support Bot")

_AGENTS: dict[str, SupportAgent] = {}


class ChatRequest(BaseModel):
    customer_message: str


class ChatResponse(BaseModel):
    conversation_id: str
    bot_message: str
    actions: list[dict[str, Any]]


class RunDevRequest(BaseModel):
    scenario_id: int | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_stateless(req: ChatRequest) -> ChatResponse:
    conv_id = str(uuid4())
    agent = SupportAgent()
    _AGENTS[conv_id] = agent
    result = agent.respond(req.customer_message)
    return ChatResponse(
        conversation_id=conv_id, bot_message=result.bot_message, actions=result.actions
    )


@app.post("/chat/{conversation_id}", response_model=ChatResponse)
def chat_continue(conversation_id: str, req: ChatRequest) -> ChatResponse:
    agent = _AGENTS.get(conversation_id)
    if agent is None:
        agent = SupportAgent()
        _AGENTS[conversation_id] = agent
    result = agent.respond(req.customer_message)
    return ChatResponse(
        conversation_id=conversation_id,
        bot_message=result.bot_message,
        actions=result.actions,
    )


@app.post("/run-dev")
def run_dev(req: RunDevRequest) -> dict[str, Any]:
    if not os.environ.get("CANDIDATE_TOKEN"):
        raise HTTPException(500, "CANDIDATE_TOKEN not set")
    with SimulatorClient() as sim:
        log = run_session(sim, "dev", req.scenario_id)
    return {
        "session_id": log.session_id,
        "scenario_id": log.scenario_id,
        "close_reason": log.close_reason,
        "turns": log.turns,
    }
