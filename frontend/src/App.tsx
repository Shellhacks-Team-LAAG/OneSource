import { useEffect, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { askApi, getConnections, startAuthorize, type AskResponse, type ConnectionsStatus } from "./lib/api";
import AnswerCard from "./components/AnswerCard";
import TracePanel from "./components/TracePanel";

function AskPage() {
  const [q, setQ] = useState("How to implement OneSource");
  const [resp, setResp] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setErr(null); setResp(null); setLoading(true);
    try {
      const r = await askApi(q);
      setResp(r);
    } catch (e: any) {
      setErr(e.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>Ask</h2>
      <div style={{display:"flex", gap:8}}>
        <input
          value={q}
          onChange={(e)=>setQ(e.target.value)}
          placeholder="Ask about deploys, runbooks, etc."
          style={{flex:1, padding:8}}
        />
        <button onClick={submit} disabled={loading || !q.trim()}>
          {loading ? "Asking…" : "Ask"}
        </button>
      </div>
      {err && <div style={{color:"crimson", marginTop:8}}>{err}</div>}
      {resp && <AnswerCard data={resp} />}
    </div>
  );
}

function ConnectionsPage() {
  const [status, setStatus] = useState<ConnectionsStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      setErr(null);
      const s = await getConnections();
      setStatus(s);
    } catch (e: any) {
      setErr(e.message || "Failed to load connections");
    }
  }

  useEffect(()=>{ refresh(); }, []);

  async function openAuth(provider: "slack"|"drive"|"github") {
    try {
      const r = await startAuthorize(provider);
      window.open(r.authorize_url, "_blank");
    } catch (e: any) {
      alert(e.message || "Failed to start authorize");
    }
  }

  return (
    <div>
      <h2>Connections</h2>
      {err && <div style={{color:"crimson"}}>{err}</div>}
      {!status ? <div>Loading…</div> : (
        <div style={{display:"grid", gridTemplateColumns:"150px 1fr 1fr", gap:8}}>
          <div>Slack</div>
          <div>{status.slack ? "✅ Connected" : "❌ Not connected"}</div>
          <button onClick={() => openAuth("slack")}>Authorize</button>

          <div>Drive</div>
          <div>{status.drive ? "✅ Connected" : "❌ Not connected"}</div>
          <button onClick={() => openAuth("drive")}>Authorize</button>

          <div>GitHub</div>
          <div>{status.github ? "✅ Connected" : "❌ Not connected"}</div>
          <button onClick={() => openAuth("github")}>Authorize</button>
        </div>
      )}
      <p style={{marginTop:12, fontSize:12, opacity:0.8}}>
        After approving in the new tab, the backend stores tokens. Refresh to see status flip.
      </p>
    </div>
  );
}

export default function App() {
  return (
    <div style={{maxWidth: 900, margin: "0 auto", padding: 16}}>
      <header style={{display:"flex", gap:16, alignItems:"center", marginBottom: 16}}>
        <h1 style={{margin:0}}>OneSource</h1>
        <nav style={{display:"flex", gap:12}}>
          <Link to="/">Ask</Link>
          <Link to="/connections">Connections</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<AskPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/trace/:id" element={<TracePanel />} />
      </Routes>
    </div>
  );
}
