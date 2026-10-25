"""Client for the capstone school agent (adk-a2a-mcp-education-capstone), reached over A2A.

The agent is discovered through the Agent Registry by name (`education_root_agent`), so no
URL is hard-coded. If the registry is down, it falls back to SCHOOL_A2A_URL.
"""

import os

import httpx
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

AGENT_REGISTRY_URL = os.getenv("AGENT_REGISTRY_URL", "http://localhost:8003")
SCHOOL_AGENT_NAME = os.getenv("SCHOOL_AGENT_NAME", "education_root_agent")
SCHOOL_A2A_URL = os.getenv("SCHOOL_A2A_URL", "http://localhost:8002")  # fallback only

_runners: dict[str, InMemoryRunner] = {}  # one runner per discovered agent card URL


async def discover_card_url() -> tuple[str, str]:
    """Return (agent card URL, how it was found): 'registry' or 'fallback'."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{AGENT_REGISTRY_URL}/agents/{SCHOOL_AGENT_NAME}")
            resp.raise_for_status()
            return resp.json()["card_url"], "registry"
    except (httpx.HTTPError, KeyError):
        return f"{SCHOOL_A2A_URL}{AGENT_CARD_WELL_KNOWN_PATH}", "fallback"


def runner_for(card_url: str) -> InMemoryRunner:
    if card_url not in _runners:
        school_agent = RemoteA2aAgent(
            name="school_agent",
            description="California schools capstone agent (data + insights), reached over A2A.",
            agent_card=card_url,
        )
        _runners[card_url] = InMemoryRunner(agent=school_agent, app_name="school_agent")
    return _runners[card_url]


async def ask_school_agent(question: str) -> str:
    card_url, source = await discover_card_url()
    print(f"school agent: {card_url} (found via {source})")
    runner = runner_for(card_url)
    session = await runner.session_service.create_session(app_name="school_agent", user_id="voice")
    message = types.Content(role="user", parts=[types.Part(text=question)])
    texts: list[str] = []
    try:
        async for event in runner.run_async(user_id="voice", session_id=session.id, new_message=message):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and not part.thought and part.text not in texts:
                        texts.append(part.text)
    except Exception as exc:
        return f"The school agent is not reachable at {card_url} ({exc}). Is the capstone running?"
    # The last text is the final answer (earlier ones are intermediate agent messages).
    return texts[-1].strip() if texts else "The school agent returned no answer."
