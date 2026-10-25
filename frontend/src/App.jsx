import { useState } from 'react'
import './App.css'
import AgentRegistry from './AgentRegistry.jsx'
import GroqVoice from './GroqVoice.jsx'
import RealtimeVoice from './RealtimeVoice.jsx'

const MODES = {
  groq: {
    label: 'Groq',
    subtitle: 'Groq Whisper + LLM voice agent → delegates questions to a Google ADK agent with Google Search',
  },
  openai: {
    label: 'OpenAI Realtime',
    subtitle: 'OpenAI Realtime voice agent → delegates questions to a Google ADK agent with Google Search',
  },
}

export default function App() {
  const [mode, setMode] = useState('groq')

  return (
    <main className="app">
      <header>
        <h1>🎙️ Voice Agent</h1>
        <p className="subtitle">{MODES[mode].subtitle}</p>
      </header>

      <AgentRegistry />

      <div className="tabs">
        {Object.entries(MODES).map(([key, m]) => (
          <button
            key={key}
            className={`tab ${mode === key ? 'active' : ''}`}
            onClick={() => setMode(key)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* key resets the component (and closes any session) when switching modes */}
      {mode === 'groq' ? <GroqVoice key="groq" /> : <RealtimeVoice key="openai" />}
    </main>
  )
}
