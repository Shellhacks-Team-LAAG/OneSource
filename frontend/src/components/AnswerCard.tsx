import { Link } from "react-router-dom";
import type { AskResponse } from "../lib/api";

function pct(n: number) { return Math.round(n * 100); }

export default function AnswerCard({ data }: { data: AskResponse }) {
  return (
    <div style={{marginTop:16, padding:12, border:"1px solid #eee", borderRadius:8}}>
      {data.policy_banner && (
        <div style={{background:"#fff8e1", padding:8, borderRadius:6, marginBottom:8}}>
          {data.policy_banner}
        </div>
      )}

      <div style={{marginBottom:8, whiteSpace:"pre-wrap"}}>{data.answer}</div>

      <div style={{display:"flex", gap:8, alignItems:"center", fontSize:13}}>
        <span>Confidence: <strong>{pct(data.confidence)}%</strong></span>
        <span>•</span>
        <span>Freshness: {new Date(data.freshness).toLocaleString()}</span>
        <span>•</span>
        <Link to={`/trace/${data.trace_id}`}>View Trace</Link>
      </div>

      <div style={{marginTop:8}}>
        <div style={{fontWeight:600, marginBottom:4}}>Citations</div>
        <ul style={{margin:0, paddingLeft:18}}>
          {data.citations.map((c, i)=>(
            <li key={i}><a href={c.url} target="_blank" rel="noreferrer">{c.label}</a></li>
          ))}
        </ul>
      </div>
    </div>
  );
}
