"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Action, ActionListResponse } from "@/lib/api";

// HR admin uses GET /actions and correlates via conversation_id for now
// (Phase 4 GET /conversations list is not yet implemented — uses actions as proxy)

export default function ConversationsPage() {
  const [actions, setActions] = useState<Action[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<ActionListResponse>("/actions")
      .then((res) => setActions(res.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Group by conversation_id
  const byConv = actions.reduce<Record<string, Action[]>>((acc, a) => {
    const key = (a as unknown as { conversation_id?: string }).conversation_id || "unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(a);
    return acc;
  }, {});

  return (
    <div style={{ padding: 32 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>Conversations</h1>
      <p style={{ color: "#64748b", fontSize: 13, marginBottom: 24 }}>
        Percakapan yang menghasilkan actions
      </p>

      {loading ? (
        <p style={{ color: "#94a3b8" }}>Memuat...</p>
      ) : Object.entries(byConv).length === 0 ? (
        <p style={{ color: "#94a3b8" }}>Belum ada conversation dengan actions</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Object.entries(byConv).map(([convId, convActions]) => (
            <div key={convId} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>
                    Conversation #{convId.slice(0, 8)}...
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                    {convActions.length} action(s) terkait
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {convActions.map((a) => (
                  <div key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "#f8fafc", borderRadius: 8 }}>
                    <div>
                      <span style={{ fontSize: 13, color: "#1e293b" }}>{a.title}</span>
                      <span style={{ fontSize: 11, color: "#94a3b8", marginLeft: 8 }}>{a.type}</span>
                    </div>
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: a.status === "completed" ? "#f0fdf4" : "#fef3c7", color: a.status === "completed" ? "#166534" : "#92400e" }}>
                      {a.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
