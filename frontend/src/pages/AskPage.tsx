import React, { useState } from "react";
import { ask } from "../lib/api";
import type { AskResponse } from "../lib/api";
import AnswerCard from "../components/AnswerCard";

export default function AskPage() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    setLoading(true);
    try {
      const data = await ask(query);
      setAnswer(data);
    } catch (err) {
      console.error("Ask failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-xl mb-4">Ask a Question</h1>

      <div className="flex gap-2 mb-4">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type your question..."
          className="border p-2 flex-1 rounded"
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          className="px-3 py-2 bg-blue-500 text-white rounded disabled:opacity-60"
        >
          {loading ? "Asking..." : "Ask"}
        </button>
      </div>

      {answer && (
        <AnswerCard
          answer={answer.answer}
          citations={answer.citations?.map((c) => c.url) ?? []}
          freshness={answer.freshness}
          confidence={answer.confidence}
          traceId={answer.trace_id ?? ""}
        />
      )}
    </div>
  );
}
