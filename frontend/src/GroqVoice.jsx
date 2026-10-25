import { useRef, useState } from 'react'
import Transcript from './Transcript.jsx'

// Voice agent built from Groq pieces (Groq has no realtime speech-to-speech API):
//   mic → Groq Whisper (speech-to-text) → Groq LLM with two tools:
//     ask_research_agent → Google ADK agent (Google Search)
//     ask_school_agent   → capstone school agent (over A2A)
//   → spoken reply (Groq TTS, or the browser's voice).

export default function GroqVoice() {
  const [status, setStatus] = useState('idle') // idle | recording | thinking | speaking
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const historyRef = useRef([]) // chat turns sent to the LLM
  const recorderRef = useRef(null)
  const chunksRef = useRef([])

  const add = (role, content) => setMessages((m) => [...m, { role, content }])

  async function speak(reply) {
    setStatus('speaking')
    try {
      const res = await fetch('/api/groq/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: reply }),
      })
      if (res.ok) {
        const audio = new Audio(URL.createObjectURL(await res.blob()))
        await new Promise((resolve) => {
          audio.onended = audio.onerror = resolve
          audio.play().catch(resolve)
        })
        return
      }
      // Groq TTS unavailable: use the browser's built-in voice.
      await new Promise((resolve) => {
        const utterance = new SpeechSynthesisUtterance(reply)
        utterance.onend = utterance.onerror = resolve
        speechSynthesis.speak(utterance)
      })
    } finally {
      setStatus('idle')
    }
  }

  async function respond(userText) {
    add('user', userText)
    historyRef.current.push({ role: 'user', content: userText })
    setStatus('thinking')
    try {
      const res = await fetch('/api/groq/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: historyRef.current }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail)
      for (const d of data.delegations) {
        add('tool', `🔀 Delegated to ${d.agent}: "${d.question}"`)
        add('tool', `🔎 ${d.agent} answered: ${d.answer}`)
      }
      add('assistant', data.reply)
      historyRef.current.push({ role: 'assistant', content: data.reply })
      await speak(data.reply)
    } catch (err) {
      add('error', err.message)
      setStatus('idle')
    }
  }

  async function startRecording() {
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(mic)
      chunksRef.current = []
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
      recorder.onstop = async () => {
        mic.getTracks().forEach((t) => t.stop())
        setStatus('thinking')
        const form = new FormData()
        form.append('audio', new Blob(chunksRef.current, { type: recorder.mimeType }), 'speech.webm')
        try {
          const res = await fetch('/api/groq/transcribe', { method: 'POST', body: form })
          const data = await res.json()
          if (!res.ok) throw new Error(data.detail)
          if (data.text) await respond(data.text)
          else setStatus('idle')
        } catch (err) {
          add('error', `Transcription failed: ${err.message}`)
          setStatus('idle')
        }
      }
      recorder.start()
      recorderRef.current = recorder
      setStatus('recording')
    } catch (err) {
      add('error', `Microphone error: ${err.message}`)
    }
  }

  function stopRecording() {
    recorderRef.current?.stop()
    recorderRef.current = null
  }

  function sendText(e) {
    e.preventDefault()
    if (!text.trim() || status !== 'idle') return
    respond(text.trim())
    setText('')
  }

  const labels = {
    idle: 'Ready',
    recording: 'Listening… click Stop when done',
    thinking: 'Thinking (may delegate to the research agent)…',
    speaking: 'Speaking…',
  }

  return (
    <>
      <div className="controls">
        {status === 'recording' ? (
          <button className="btn stop" onClick={stopRecording}>■ Stop &amp; send</button>
        ) : (
          <button className="btn start" onClick={startRecording} disabled={status !== 'idle'}>
            🎤 Ask a question
          </button>
        )}
        <span className={`dot ${status === 'idle' ? 'live' : 'connecting'}`} />
        <span className="status">{labels[status]}</span>
      </div>

      <Transcript messages={messages} />

      <form className="text-input" onSubmit={sendText}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Or type a question…"
          disabled={status !== 'idle'}
        />
        <button className="btn" disabled={status !== 'idle'}>Send</button>
      </form>
    </>
  )
}
