// src/pages/Trace.tsx
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getTrace } from "../lib/api";

export default function Trace() {
  const { id } = useParams<{id: string}>();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await getTrace(id!));
      } catch (e: any) {
        setErr(e.message || String(e));
      }
    })();
  }, [id]);

  if (err) return <div style={{ padding: 16, color: "crimson" }}>{err}</div>;
  if (!data) return <div style={{ padding: 16 }}>Loading…</div>;

  return (
    <div style={{ padding: 16 }}>
      <h2>Trace {id}</h2>
      <pre style={{ background: "#f7f7f7", padding: 12, borderRadius: 6 }}>
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
