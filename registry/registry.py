"""Agent Registry: a small directory of A2A agents.

Agents register the URL of their A2A Agent Card; the registry fetches and stores the card.
Other agents look agents up by name instead of hard-coding URLs.

POST /agents          {"card_url": "http://localhost:8002/.well-known/agent-card.json"}
GET  /agents          all registered agents, with a live health check
GET  /agents/{name}   one agent's entry (card_url, url, card)

Run:  uvicorn registry:app --app-dir registry --port 8003
"""

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Agent Registry")
agents: dict[str, dict] = {}  # name -> entry (in memory; agents re-register on startup)


class Registration(BaseModel):
    card_url: str


def endpoint_of(card: dict) -> str:
    """The agent's A2A endpoint, from either card format (a2a-sdk 1.x or 0.x)."""
    interfaces = card.get("supportedInterfaces") or card.get("additionalInterfaces") or []
    return (interfaces[0].get("url") if interfaces else None) or card.get("url", "")


async def fetch_card(client: httpx.AsyncClient, card_url: str) -> dict:
    resp = await client.get(card_url, timeout=5)
    resp.raise_for_status()
    return resp.json()


@app.post("/agents")
async def register(reg: Registration) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            card = await fetch_card(client, reg.card_url)
        except Exception as exc:
            raise HTTPException(400, f"Could not fetch agent card at {reg.card_url}: {exc}")
    entry = {
        "name": card["name"],
        "description": card.get("description", ""),
        "card_url": reg.card_url,
        "url": endpoint_of(card),
        "skills": [s.get("name") for s in card.get("skills", [])],
        "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "card": card,
    }
    agents[entry["name"]] = entry
    print(f"Registered {entry['name']} -> {entry['url']}")
    return {k: v for k, v in entry.items() if k != "card"}


@app.get("/agents")
async def list_agents() -> list[dict]:
    """All agents, each with status 'up' or 'down' from a quick card fetch."""
    async with httpx.AsyncClient() as client:
        async def check(entry: dict) -> dict:
            try:
                await fetch_card(client, entry["card_url"])
                status = "up"
            except Exception:
                status = "down"
            return {**{k: v for k, v in entry.items() if k != "card"}, "status": status}
        return list(await asyncio.gather(*(check(e) for e in agents.values())))


@app.get("/agents/{name}")
async def get_agent(name: str) -> dict:
    if name not in agents:
        raise HTTPException(404, f"No agent named {name!r} is registered")
    return agents[name]
