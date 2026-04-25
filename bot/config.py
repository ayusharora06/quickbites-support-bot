import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

SIMULATOR_BASE_URL = os.environ.get(
    "SIMULATOR_BASE_URL", "https://simulator-75lk3meynq-el.a.run.app"
).rstrip("/")
CANDIDATE_TOKEN = os.environ.get("CANDIDATE_TOKEN", "")

DB_PATH = (ROOT / os.environ.get("DB_PATH", "quickbites-candidate-starter/app.db")).resolve()
POLICY_PATH = (ROOT / os.environ.get("POLICY_PATH", "quickbites-candidate-starter/policy_and_faq.md")).resolve()

SNAPSHOT_DATE = "2026-04-13"

MAX_AGENT_ITERATIONS = 8
