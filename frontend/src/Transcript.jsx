const ROLE_LABELS = { user: 'You', assistant: 'Agent', tool: 'ADK', system: 'System', error: 'Error' }

export default function Transcript({ messages }) {
  return (
    <section className="transcript">
      {messages.length === 0 && (
        <p className="hint">
          Try: “What's the weather in San Francisco today?” or “Who won the last World Series?”
        </p>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`msg ${m.role}`}>
          <span className="role">{ROLE_LABELS[m.role]}</span>
          <span>{m.content}</span>
        </div>
      ))}
    </section>
  )
}
