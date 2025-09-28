// src/pages/Connections.tsx
import React, { useEffect, useState } from "react";
import { getConnections, startAuthorize } from "../lib/api";

export default function Connections() {
  const [st, setSt] = useState<{slack:boolean,drive:boolean,github:boolean} | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    try {
      setSt(await getConnections());
    } catch (e: any) {
      setErr(e.message || String(e));
    }
  }
  useEffect(() => { refresh(); }, []);

  async function connect(provider: "slack"|"github"|"drive") {
    try {
      const { authorize_url } = await startAuthorize(provider);
      window.open(authorize_url, "_blank");
    } catch (e: any) { setErr(e.message || String(e)); }
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Connections</h2>
      {err && <p style={{ color: "crimson" }}>{err}</p>}
      {!st ? <p>Loading…</p> : (
        <ul>
          <li>Slack: {String(st.slack)} {!st.slack && <button onClick={() => connect("slack")}>Connect</button>}</li>
          <li>Drive: {String(st.drive)} {!st.drive && <button onClick={() => connect("drive")}>Connect</button>}</li>
          <li>GitHub: {String(st.github)} {!st.github && <button onClick={() => connect("github")}>Connect</button>}</li>
        </ul>
      )}
      <button onClick={refresh}>Refresh</button>
    </div>
  );
}
