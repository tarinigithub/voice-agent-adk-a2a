import { useRef, useState } from 'react'
import Transcript from './Transcript.jsx'

// Voice agent = OpenAI Realtime over WebRTC. It has one tool, ask_research_agent,
// which forwards the question to the Google ADK agent (Google Search) on our backend.

const INSTRUCTIONS = `You are a friendly, concise voice assistant.
For questions about California public schools, districts or counties (low-income students,
funding, class sizes, STEM, graduation rates, interventions), call the ask_school_agent tool.
For any other factual question, current event, news, weather, sports, prices, or anything you
would need to look up, call the ask_research_agent tool with the user's question.
Before calling it, say a short filler like "Let me look that up."
When the tool returns, speak the answer naturally in a few sentences.
For greetings and small talk, just reply directly.`

const TOOLS = [
  {
    type: 'function',
    name: 'ask_research_agent',
    description:
      'Delegate a question to the research agent (Google ADK + Google Search). ' +
      'Returns an up-to-date answer to speak to the user.',
    parameters: {
      type: 'object',
      properties: {
        question: { type: 'string', description: "The user's question, fully self-contained." },
      },
      required: ['question'],
    },
  },
  {
    type: 'function',
    name: 'ask_school_agent',
    description:
      'Delegate a question about California public schools to the Education Insights ' +
      'capstone agent (over A2A). Returns data-backed answers and recommendations.',
    parameters: {
      type: 'object',
      properties: {
        question: { type: 'string', description: "The user's question, fully self-contained." },
      },
      required: ['question'],
    },
  },
]

// Tool name -> backend endpoint and label shown in the transcript.
const TOOL_ROUTES = {
  ask_research_agent: { url: '/api/ask', label: 'Google ADK search agent' },
  ask_school_agent: { url: '/api/ask_school', label: 'School agent (capstone, A2A)' },
}

export default function RealtimeVoice() {
  const [status, setStatus] = useState('idle') // idle | connecting | live
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false) // research agent working
  const [text, setText] = useState('')
  const pcRef = useRef(null)
  const dcRef = useRef(null)
  const micRef = useRef(null)
  const audioRef = useRef(null)

  const add = (role, content) => setMessages((m) => [...m, { role, content }])

  const send = (event) => dcRef.current?.send(JSON.stringify(event))

  async function handleToolCall({ call_id, name, arguments: args }) {
    const route = TOOL_ROUTES[name]
    if (!route) return
    const { question } = JSON.parse(args || '{}')
    add('tool', `🔀 Delegating to ${route.label}: "${question}"`)
    setBusy(true)
    let answer
    try {
      const res = await fetch(route.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      answer = (await res.json()).answer
    } catch (err) {
      answer = `The research agent failed: ${err.message}`
    }
    setBusy(false)
    add('tool', `🔎 ${route.label} answered: ${answer}`)
    send({
      type: 'conversation.item.create',
      item: { type: 'function_call_output', call_id, output: JSON.stringify({ answer }) },
    })
    send({ type: 'response.create' })
  }

  function handleEvent(event) {
    switch (event.type) {
      case 'conversation.item.input_audio_transcription.completed':
        if (event.transcript?.trim()) add('user', event.transcript.trim())
        break
      case 'response.output_audio_transcript.done':
        if (event.transcript?.trim()) add('assistant', event.transcript.trim())
        break
      case 'response.function_call_arguments.done':
        handleToolCall(event)
        break
      case 'error':
        add('error', event.error?.message || 'Unknown error')
        break
    }
  }

  async function start() {
    setStatus('connecting')
    try {
      // 1. Ephemeral key from our backend (the real OpenAI key never reaches the browser).
      const sessionRes = await fetch('/api/session', { method: 'POST' })
      if (!sessionRes.ok) throw new Error((await sessionRes.json()).detail)
      const { client_secret, model } = await sessionRes.json()

      // 2. WebRTC: play the model's audio, send our mic, open the events data channel.
      const pc = new RTCPeerConnection()
      pc.ontrack = (e) => (audioRef.current.srcObject = e.streams[0])
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true })
      mic.getTracks().forEach((t) => pc.addTrack(t, mic))

      const dc = pc.createDataChannel('oai-events')
      dc.onmessage = (e) => handleEvent(JSON.parse(e.data))
      dc.onopen = () => {
        send({
          type: 'session.update',
          session: {
            type: 'realtime',
            instructions: INSTRUCTIONS,
            tools: TOOLS,
            tool_choice: 'auto',
            audio: { input: { transcription: { model: 'gpt-4o-mini-transcribe' } } },
          },
        })
        setStatus('live')
        add('system', 'Connected. Start talking!')
      }

      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      const sdpRes = await fetch(`https://api.openai.com/v1/realtime/calls?model=${model}`, {
        method: 'POST',
        body: offer.sdp,
        headers: { Authorization: `Bearer ${client_secret}`, 'Content-Type': 'application/sdp' },
      })
      if (!sdpRes.ok) throw new Error(await sdpRes.text())
      await pc.setRemoteDescription({ type: 'answer', sdp: await sdpRes.text() })

      pcRef.current = pc
      dcRef.current = dc
      micRef.current = mic
    } catch (err) {
      add('error', `Could not connect: ${err.message}`)
      stop()
    }
  }

  function stop() {
    dcRef.current?.close()
    pcRef.current?.close()
    micRef.current?.getTracks().forEach((t) => t.stop())
    pcRef.current = dcRef.current = micRef.current = null
    setStatus('idle')
    setBusy(false)
  }

  function sendText(e) {
    e.preventDefault()
    if (!text.trim() || status !== 'live') return
    add('user', text.trim())
    send({
      type: 'conversation.item.create',
      item: { type: 'message', role: 'user', content: [{ type: 'input_text', text: text.trim() }] },
    })
    send({ type: 'response.create' })
    setText('')
  }

  return (
    <>
      <div className="controls">
        {status === 'live' ? (
          <button className="btn stop" onClick={stop}>■ End conversation</button>
        ) : (
          <button className="btn start" onClick={start} disabled={status === 'connecting'}>
            {status === 'connecting' ? 'Connecting…' : '● Start talking'}
          </button>
        )}
        <span className={`dot ${status}`} />
        <span className="status">
          {status === 'live' ? (busy ? 'Research agent searching…' : 'Listening') : status}
        </span>
      </div>

      <Transcript messages={messages} />

      <form className="text-input" onSubmit={sendText}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={status === 'live' ? 'Or type a question…' : 'Start a conversation first'}
          disabled={status !== 'live'}
        />
        <button className="btn" disabled={status !== 'live'}>Send</button>
      </form>

      <audio ref={audioRef} autoPlay />
    </>
  )
}
