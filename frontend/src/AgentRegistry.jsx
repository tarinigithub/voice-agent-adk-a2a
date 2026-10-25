import { useEffect, useState } from 'react'

// Shows the agents listed in the Agent Registry (via GET /api/agents).
export default function AgentRegistry() {
  const [agents, setAgents] = useState(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      const res = await fetch('/api/agents')
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail)
      setAgents(data)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <details className="registry">
      <summary>
        🗂️ Agent Registry{' '}
        <span className="muted">{agents ? `(${agents.length} registered)` : ''}</span>
      </summary>
      {error && <p className="msg error">{error}</p>}
      {agents?.length === 0 && <p className="muted">No agents registered yet.</p>}
      {agents?.map((a) => (
        <div key={a.name} className="registry-row">
          <span className={`dot ${a.status === 'up' ? 'live' : ''}`} />
          <div>
            <strong>{a.name}</strong> <code>{a.url}</code>
            <div className="muted">{a.description}</div>
          </div>
        </div>
      ))}
      <button className="btn small" onClick={load}>Refresh</button>
    </details>
  )
}
