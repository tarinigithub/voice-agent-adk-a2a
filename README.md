# Voice Agent + Google ADK Research Agent

> Companion repo: **[adk-a2a-mcp-education-capstone](https://github.com/tarinigithub/adk-a2a-mcp-education-capstone)**,
> the Education Insights capstone this voice agent talks to over A2A.
> Full design: [DESIGN.md](DESIGN.md).

1. A simple **voice agent** with a React UI, in two modes you switch between with a toggle:
   - **Groq** (default): Groq Whisper (speech-to-text), Groq `gpt-oss` (LLM with tools), and
     Groq Orpheus text-to-speech (falls back to the browser's built-in voice)
   - **OpenAI Realtime**: speech-to-speech over WebRTC (needs an OpenAI key)
2. A simple **Google ADK agent** with the **`google_search`** tool. In both modes, the voice
   agent **delegates** user questions to it and speaks the answer.
3. **Voice front end for the capstone:** school questions are delegated over **A2A** to the
   Education Insights agent in `../adk-a2a-mcp-education-capstone`.

## Two delegate agents

| Voice agent tool | Delegates to | How |
|---|---|---|
| `ask_research_agent` | Google ADK search agent (`backend/research_agent/`) | In-process ADK runner |
| `ask_school_agent` | Capstone root agent (California schools data + insights; its data agent queries the database through an **MCP server**) | A2A, endpoint discovered through the Agent Registry, via ADK `RemoteA2aAgent` (`backend/school_agent.py`) |

The voice model picks the tool. School questions ("Which Fresno schools have the most
low-income students?") go to the capstone, and everything else factual ("Weather in Seattle?")
goes to Google Search. `start.sh` starts the capstone's A2A servers (ports 8001 and 8002)
automatically when the capstone folder sits next to this one (set `CAPSTONE_DIR` to override).

## Agent Registry

`registry/registry.py` (port 8003, started first by `start.sh`) is a small directory of A2A
agents. The capstone's agents **register themselves** on startup by posting their Agent Card URL,
and the voice backend **discovers** the school agent by name (`education_root_agent`) instead
of using a hard-coded URL. If the registry is down, it falls back to `SCHOOL_A2A_URL`.

| Endpoint | Purpose |
|---|---|
| `POST /agents` `{"card_url": ...}` | Register an agent (the registry fetches and stores its card) |
| `GET /agents` | All agents, with a live up/down status |
| `GET /agents/{name}` | Look up one agent by name |

The UI shows the registry in a collapsible **🗂️ Agent Registry** panel (via `GET /api/agents`).
Try `curl localhost:8003/agents` while everything is running.

## Groq mode

Groq has no realtime speech-to-speech API, so this mode chains the pieces together,
one turn at a time:

```
🎤 record ─▶ /api/groq/transcribe (Whisper) ─▶ /api/groq/chat (gpt-oss + ask_research_agent tool)
                                                     │ tool call
                                                     ▼
                                              Google ADK agent ─▶ google_search
                                                     │ answer
🔊 speak ◀── /api/groq/speak (Orpheus TTS, or browser voice) ◀── final reply
```

Click **🎤 Ask a question**, speak, then click **Stop & send**.

To use Groq's voice instead of the browser's, accept the Orpheus model terms once at
https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english
(until you do, `/api/groq/speak` returns 503 and the browser voice is used).

## OpenAI Realtime mode

```
 🎤 Browser (React)  ──WebRTC audio──▶  OpenAI Realtime (gpt-realtime)
        │                                     │ calls tool ask_research_agent(question)
        │  ◀──── function call event ─────────┘
        │
        └──POST /api/ask──▶ FastAPI backend ──▶ Google ADK agent ──▶ google_search
                                    │                (Gemini)
        ◀──────── answer ───────────┘
        └── function_call_output ──▶ OpenAI Realtime ──▶ 🔊 speaks the answer
```

### How the delegation works

- The browser connects to OpenAI Realtime and registers one tool, `ask_research_agent`
  (see `frontend/src/RealtimeVoice.jsx`).
- When the user asks a factual or current question, the voice model calls that tool.
- The browser sends the question to `POST /api/ask`. The backend runs the ADK
  `research_agent` (`backend/research_agent/agent.py`), which searches Google.
- The answer goes back to the voice model as the tool result, and the model speaks it.
- The transcript shows each hand-off (🔀 delegating / 🔎 ADK answered).

The real OpenAI key stays on the server. `POST /api/session` gives the browser a
short-lived token instead.

## Setup

Clone both repos **side by side** (`start.sh` looks for the capstone in `../adk-a2a-mcp-education-capstone`),
and set up the capstone first as described in its README:

```bash
git clone https://github.com/tarinigithub/voice-agent-adk-a2a.git
git clone https://github.com/tarinigithub/adk-a2a-mcp-education-capstone.git
```

Then, in `voice-agent-adk-a2a`:

```bash
# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # set GOOGLE_API_KEY, plus GROQ_API_KEY and/or OPENAI_API_KEY

# frontend
cd ../frontend
npm install
```

## Run

```bash
./start.sh
```

Open http://localhost:5173, pick **Groq** or **OpenAI Realtime**, allow microphone access,
and ask something like *"What's the weather in Seattle today?"* or *"Who won the last Super
Bowl?"*. You can also type questions.

To try the ADK agent on its own, either use its chat UI:
```bash
cd backend && .venv/bin/adk web      # http://localhost:8000, pick research_agent
```
or call the API while the backend is running:
```bash
curl -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
     -d '{"question": "What is the latest stable Python version?"}'
```

## Files

| Path | Purpose |
|---|---|
| `backend/main.py` | FastAPI: Groq endpoints (transcribe, chat with tool, speak), `/api/session` (Realtime token), `/api/ask` (runs the ADK agent) |
| `backend/research_agent/agent.py` | Google ADK agent with the `google_search` tool |
| `backend/school_agent.py` | A2A client for the capstone school agent; discovers it via the registry |
| `registry/registry.py` | Agent Registry service (port 8003) |
| `frontend/src/AgentRegistry.jsx` | UI panel listing registered agents |
| `frontend/src/App.jsx` | React UI shell with the Groq / OpenAI toggle |
| `frontend/src/GroqVoice.jsx` | Groq mode: record, transcribe, chat, speak |
| `frontend/src/RealtimeVoice.jsx` | OpenAI mode: WebRTC voice session and tool-call handling |
| `frontend/src/Transcript.jsx` | Shared transcript view |
| `frontend/vite.config.js` | Proxies `/api` to the backend |
| `start.sh` | Starts the backend and frontend together |
