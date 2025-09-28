// src/components/TracePanel.tsx
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getTrace } from "../lib/api";

type ProviderFlags = { timeout?: boolean; error?: string; rate_limited?: number };

type Trace = {
  trace_id: string;
  query: string;
  timings_ms: Record<string, number>;
  provider_flags?: Record<string, ProviderFlags>;
  candidates: Array<{ source: string; url: string; score: number; reasons: string[] }>;
  chosen: { url: string; score: number; explanations: string[] };
  policy: { redactions: string[]; conflict: boolean };
};

export default function TracePanel() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Trace | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function load() {
      if (!id) return;
      try {
        setErr(null);
        setLoading(true);
        const t = await getTrace<Trace>(id);
        setData(t);
      } catch (e: any) {
        setErr(e.message || "Failed to load trace");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading && !data) return <div>Loading…</div>;
  if (err) return <div style={{ color: "crimson" }}>{err}</div>;
  if (!data) return null;

  return (
    <div>
      <h2>Trace</h2>
      <div style={{ marginBottom: 8 }}>
        Query: <strong>{data.query}</strong>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>Timings (ms)</div>
        <pre style={{ background: "#f7f7f7", padding: 8, borderRadius: 6 }}>
{JSON.stringify(data.timings_ms, null, 2)}
        </pre>
      </div>

      {data.provider_flags && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontWeight: 600 }}>Provider flags</div>
          <pre style={{ background: "#f7f7f7", padding: 8, borderRadius: 6 }}>
{JSON.stringify(data.provider_flags, null, 2)}
          </pre>
        </div>
      )}

      <div style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>Candidates</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>Source</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>URL</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>Score</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>Reasons</th>
            </tr>
          </thead>
          <tbody>
            {data.candidates.map((c, i) => (
              <tr key={i}>
                <td>{c.source}</td>
                <td>
                  <a href={c.url} target="_blank" rel="noreferrer">
                    {c.url}
                  </a>
                </td>
                <td>{c.score.toFixed(3)}</td>
                <td>{c.reasons.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>Chosen</div>
        <div>Score: {data.chosen.score.toFixed(3)}</div>
        <div>Explanations: {data.chosen.explanations.join(", ")}</div>
        {data.chosen.url && (
          <div>
            URL:{" "}
            <a href={data.chosen.url} target="_blank" rel="noreferrer">
              {data.chosen.url}
            </a>
          </div>
        )}
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>Policy</div>
        <pre style={{ background: "#f7f7f7", padding: 8, borderRadius: 6 }}>
{JSON.stringify(data.policy, null, 2)}
        </pre>
      </div>

      <Link to="/">← Back to Ask</Link>
    </div>
  );
}
