"""Google ADK research agent: answers questions using the built-in Google Search tool.

The voice agent (OpenAI Realtime) delegates user questions to this agent via POST /api/ask.
Can also be tried on its own with:  adk web   (run from the backend/ folder)
"""

import os

from google.adk.agents import Agent
from google.adk.tools import google_search

root_agent = Agent(
    name="research_agent",
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    description="Answers user questions with up-to-date information from Google Search.",
    instruction="""You answer questions for a voice assistant. Use the google_search tool
for anything factual, current, or that you are not certain about.

Your answer will be read aloud, so:
- Reply in 2-4 short, plain sentences. No markdown, bullet points, tables or URLs.
- Lead with the direct answer, then one or two supporting details.
- Spell out numbers and dates naturally (e.g. "October 23rd, 2026").""",
    tools=[google_search],
)
