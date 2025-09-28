import React, { useEffect, useState } from "react";

interface Connection {
  service: string;
  connected: boolean;
  workspace?: string;
}

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);

  // Poll or refresh connections
  const fetchConnections = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE}/connections`);
      if (res.ok) {
        const data = await res.json();
        // expected: [{ service: "slack", connected: true, workspace: "MyTeam" }]
        setConnections(data);
      } else {
        console.error("Failed to fetch connections", res.status);
      }
    } catch (err) {
      console.error("Error fetching connections:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConnections();
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-xl mb-4 font-bold">Connections</h1>

      <button
        onClick={fetchConnections}
        className="mb-4 px-3 py-2 bg-gray-200 rounded hover:bg-gray-300"
        disabled={loading}
      >
        {loading ? "Refreshing..." : "Refresh Status"}
      </button>

      <div className="space-y-4">
        {connections.map((c, idx) => (
          <div
            key={idx}
            className="p-4 border rounded shadow-sm flex justify-between items-center"
          >
            <div>
              <p className="font-semibold">{c.service.toUpperCase()}</p>
              <p className="text-sm text-gray-600">
                {c.connected
                  ? `Connected${c.workspace ? " to " + c.workspace : ""}`
                  : "Not connected"}
              </p>
            </div>

            {!c.connected ? (
              <button
                className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                onClick={() =>
                  (window.location.href = `${import.meta.env.VITE_API_BASE}/connections/${c.service}/install`)
                }
              >
                Connect
              </button>
            ) : (
              <button
                className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600"
                onClick={() =>
                  (window.location.href = `${import.meta.env.VITE_API_BASE}/connections/${c.service}/disconnect`)
                }
              >
                Disconnect
              </button>
            )}
          </div>
        ))}

        {/* Fallback manual Slack connect if backend gives no list */}
        {connections.length === 0 && (
          <button
            className="px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            onClick={() =>
              (window.location.href = `${import.meta.env.VITE_API_BASE}/connections/slack/install`)
            }
          >
            Connect Slack
          </button>
        )}
      </div>
    </div>
  );
}
