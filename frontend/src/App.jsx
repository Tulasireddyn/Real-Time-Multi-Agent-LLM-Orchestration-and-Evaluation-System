import React, { useState, useEffect } from 'react'

function App() {
  const [query, setQuery] = useState('')
  const [logs, setLogs] = useState([])
  const [result, setResult] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!query) return

    setLogs([])
    setResult(null)
    setIsProcessing(true)

    try {
      const response = await fetch('http://localhost:8000/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (data.status === 'processing') {
              setLogs(prev => [...prev, data])
            } else if (data.status === 'completed') {
              setResult(data.result)
              setIsProcessing(false)
            }
          }
        }
      }
    } catch (err) {
      console.error(err)
      setIsProcessing(false)
    }
  }

  return (
    <div className="dashboard">
      {/* Sidebar: Logs */}
      <div className="glass-card main-view">
        <h2 style={{marginTop: 0}}>Real-Time Activity</h2>
        <div className="agent-activity">
          {logs.map((log, i) => (
            <div key={i} className="activity-item">
              <span className="badge badge-orchestrator">System</span>
              <span>{log.status}...</span>
            </div>
          ))}
          {!isProcessing && logs.length === 0 && (
            <p style={{opacity: 0.5}}>No active jobs</p>
          )}
        </div>
      </div>

      {/* Main View: Input & Result */}
      <div className="main-view">
        <div className="glass-card">
          <h1>Multi-Agent Orchestrator</h1>
          <form onSubmit={handleSubmit} style={{display: 'flex', gap: '1rem'}}>
            <input 
              type="text" 
              value={query} 
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your complex query..."
              disabled={isProcessing}
            />
            <button type="submit" disabled={isProcessing}>
              {isProcessing ? 'Processing...' : 'Run Pipeline'}
            </button>
          </form>
        </div>

        {result && (
          <div className="glass-card" style={{flex: 1}}>
            <h2>Final Synthesis</h2>
            <p>{result.history.slice(-1)[0].content}</p>
            
            <h3>Provenance Map</h3>
            <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
              {result.provenance.map((p, i) => (
                <div key={i} style={{fontSize: '0.9rem', padding: '0.5rem', background: 'rgba(255,255,255,0.05)', borderRadius: '0.25rem'}}>
                  <strong>{p.source_agent}:</strong> {p.sentence}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Stats Sidebar */}
      <div className="glass-card main-view">
        <h2 style={{marginTop: 0}}>System Health</h2>
        <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
          <div>
            <label style={{opacity: 0.5}}>Token Budget</label>
            <div style={{height: '8px', background: '#334155', borderRadius: '4px', marginTop: '0.5rem'}}>
              <div style={{width: result ? '40%' : '0%', height: '100%', background: '#6366f1', borderRadius: '4px'}}></div>
            </div>
          </div>
          <div>
            <label style={{opacity: 0.5}}>Model</label>
            <p style={{margin: '0.25rem 0'}}>Llama 3 (Ollama)</p>
          </div>
          <div>
            <label style={{opacity: 0.5}}>Active Tools</label>
            <div style={{display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem'}}>
              {['Search', 'Sandbox', 'SQL', 'Reflect'].map(t => (
                <span key={t} className="badge" style={{background: '#475569'}}>{t}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
