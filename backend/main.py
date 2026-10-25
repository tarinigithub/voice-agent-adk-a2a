"""Backend for the voice agent demo.

OpenAI mode
POST /api/session         -> short-lived OpenAI Realtime client secret for the browser (keeps
                             the real OPENAI_API_KEY on the server)
Groq mode
POST /api/groq/transcribe -> speech to text (Groq Whisper)
POST /api/groq/chat       -> voice agent turn (Groq LLM); delegates to the ADK agent via a tool
POST /api/groq/speak      -> text to speech (Groq Orpheus); 503 means use the browser voice
Shared
POST /api/ask             -> runs the Google ADK research agent (Google Search) on a question
POST /api/ask_school      -> asks the capstone school agent over A2A (found via the Agent Registry)
GET  /api/agents          -> agents listed in the Agent Registry (port 8003)

Run:  uvicorn main:app --port 8000 --reload
"""

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, Response, UploadFile
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from research_agent.agent import root_agent
from school_agent import AGENT_REGISTRY_URL, ask_school_agent

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "marin")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")

# Same persona and tool as the OpenAI Realtime agent in frontend/src/RealtimeVoice.jsx.
VOICE_AGENT_PROMPT = """You are a friendly, concise voice assistant.
For questions about California public schools, school districts or counties (low-income
students, funding, spending, class sizes, STEM, AP courses, graduation rates, which schools
need help, education interventions), call the ask_school_agent tool.
For any other factual question, current event, news, weather, sports, prices, or anything you
would need to look up, call the ask_research_agent tool with the user's question.
When a tool returns, answer naturally in 2-4 short spoken sentences. If it returns a table,
summarize it: name the top two or three schools and the key number for each.
For greetings and small talk, just reply directly.
Your reply is read aloud: no markdown, lists, tables or URLs."""

ASK_RESEARCH_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_research_agent",
        "description": (
            "Delegate a question to the research agent (Google ADK + Google Search). "
            "Returns an up-to-date answer to speak to the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The user's question, fully self-contained."}
            },
            "required": ["question"],
        },
    },
}

ASK_SCHOOL_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_school_agent",
        "description": (
            "Delegate a question about California public schools to the Education Insights "
            "capstone agent (over A2A). It queries school data on demographics, funding, "
            "staffing, STEM and graduation rates, and gives evidence-based recommendations."
        ),
        "parameters": ASK_RESEARCH_AGENT_TOOL["function"]["parameters"],
    },
}

AGENT_LABELS = {
    "ask_research_agent": "Google ADK search agent",
    "ask_school_agent": "School agent (capstone, A2A)",
}

app = FastAPI(title="Voice Agent Backend")
runner = InMemoryRunner(agent=root_agent, app_name="research_agent")


@app.post("/api/session")
async def create_realtime_session() -> dict:
    """Mint an ephemeral key the browser uses to open a WebRTC call to OpenAI Realtime."""
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
        raise HTTPException(500, "OPENAI_API_KEY is not set in backend/.env")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "session": {
                    "type": "realtime",
                    "model": REALTIME_MODEL,
                    "audio": {"output": {"voice": REALTIME_VOICE}},
                }
            },
        )
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return {"client_secret": resp.json()["value"], "model": REALTIME_MODEL}


class AskRequest(BaseModel):
    question: str


async def run_research_agent(question: str) -> str:
    session = await runner.session_service.create_session(app_name="research_agent", user_id="voice")
    message = types.Content(role="user", parts=[types.Part(text=question)])
    answer = ""
    async for event in runner.run_async(user_id="voice", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            answer = "".join(p.text or "" for p in event.content.parts if not p.thought)
    return answer.strip() or "Sorry, I couldn't find an answer to that."


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    """Delegate a question from the voice agent to the Google ADK research agent."""
    return {"answer": await run_research_agent(req.question)}


@app.post("/api/ask_school")
async def ask_school(req: AskRequest) -> dict:
    """Delegate a school question to the capstone agent over A2A."""
    return {"answer": await ask_school_agent(req.question)}


TOOL_HANDLERS = {
    "ask_research_agent": run_research_agent,
    "ask_school_agent": ask_school_agent,
}


@app.get("/api/agents")
async def list_registered_agents() -> list[dict]:
    """Agents in the Agent Registry (for the UI's registry panel)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_REGISTRY_URL}/agents")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"Agent registry not reachable at {AGENT_REGISTRY_URL}: {exc}")


# ---------- Groq mode ----------

def groq_headers() -> dict:
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("your_"):
        raise HTTPException(500, "GROQ_API_KEY is not set in backend/.env")
    return {"Authorization": f"Bearer {GROQ_API_KEY}"}


@app.post("/api/groq/transcribe")
async def groq_transcribe(audio: UploadFile) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{GROQ_URL}/audio/transcriptions",
            headers=groq_headers(),
            data={"model": GROQ_STT_MODEL},
            files={"file": (audio.filename or "speech.webm", await audio.read(), audio.content_type)},
        )
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return {"text": resp.json()["text"].strip()}


class ChatRequest(BaseModel):
    messages: list[dict]  # prior turns: [{"role": "user"|"assistant", "content": "..."}]


@app.post("/api/groq/chat")
async def groq_chat(req: ChatRequest) -> dict:
    """One voice-agent turn. If the model calls ask_research_agent, run the ADK agent and
    feed the answer back so the model can phrase the spoken reply."""
    messages = [{"role": "system", "content": VOICE_AGENT_PROMPT}, *req.messages]
    delegations = []
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(3):  # at most a couple of tool rounds
            resp = await client.post(
                f"{GROQ_URL}/chat/completions",
                headers=groq_headers(),
                json={"model": GROQ_CHAT_MODEL, "messages": messages,
                      "tools": [ASK_RESEARCH_AGENT_TOOL, ASK_SCHOOL_AGENT_TOOL],
                      "tool_choice": "auto"},
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            msg = resp.json()["choices"][0]["message"]
            if not msg.get("tool_calls"):
                return {"reply": (msg.get("content") or "").strip(), "delegations": delegations}

            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": msg["tool_calls"]})
            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                question = json.loads(call["function"]["arguments"] or "{}").get("question", "")
                answer = await TOOL_HANDLERS.get(name, run_research_agent)(question)
                delegations.append({"agent": AGENT_LABELS.get(name, name),
                                    "question": question, "answer": answer})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps({"answer": answer})})
    return {"reply": delegations[-1]["answer"] if delegations else "", "delegations": delegations}


class SpeakRequest(BaseModel):
    text: str


@app.post("/api/groq/speak")
async def groq_speak(req: SpeakRequest) -> Response:
    """Groq text-to-speech. Returns 503 if unavailable (e.g. model terms not accepted),
    and the browser falls back to its built-in voice."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{GROQ_URL}/audio/speech",
            headers=groq_headers(),
            json={"model": GROQ_TTS_MODEL, "voice": GROQ_TTS_VOICE,
                  "input": req.text[:1000], "response_format": "wav"},
        )
    if resp.status_code != 200:
        return Response(resp.text, status_code=503, media_type="application/json")
    return Response(resp.content, media_type="audio/wav")
