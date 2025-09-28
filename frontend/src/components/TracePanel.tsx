import { useEffect, useState } from "react";
import { getTrace } from "../lib/api";
import type { TraceResponse } from "../lib/api";

export default function TracePanel({
  traceId,
  isOpen,
  onClose,
}: {
  traceId: string | undefined;
  isOpen: boolean;
  onClose: () => void;
}) {
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !traceId) return;
    (async () => {
      setLoading(true);
      try {
        const data = await getTrace(traceId);
        setTrace(data);
      } catch (err) {
        console.error("Trace fetch failed:", err);
      } finally {
        setLoading(false);
      }
    })();
  }, [isOpen, traceId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-lg p-4 w-2/3 max-h-[80vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold">Trace Details</h2>
          <button
            className="px-2 py-1 bg-gray-200 rounded hover:bg-gray-300"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        {loading && <p>Loading trace...</p>}

        {!loading && trace && (
          <div>
            <p className="mb-2 text-sm text-gray-600">
              Query: {trace.query}
            </p>
            <p className="mb-4 text-sm text-gray-600">
              Trace ID: {trace.trace_id}
            </p>

            <h3 className="font-semibold mb-2">Fusion Decision</h3>
            <p className="mb-4">{trace.fusion.rationale}</p>

            <h3 className="font-semibold mb-2">Candidates</h3>
            <ul className="space-y-2">
              {trace.candidates.map((c, idx) => (
                <li
                  key={idx}
                  className="border p-2 rounded bg-gray-50 text-sm"
                >
                  <p>
                    <strong>Source:</strong> {c.source}
                  </p>
                  <p>
                    <strong>Snippet:</strong> {c.snippet}
                  </p>
                  <p>
                    <strong>Score:</strong> {c.raw_score}
                  </p>
                  <p>
                    <strong>Authority:</strong>{" "}
                    {JSON.stringify(c.authority)}
                  </p>
                  <p>
                    <strong>URL:</strong>{" "}
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-500 underline"
                    >
                      {c.url}
                    </a>
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!loading && !trace && <p>No trace data available.</p>}
      </div>
    </div>
  );
}
