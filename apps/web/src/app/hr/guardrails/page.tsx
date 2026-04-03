"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditLog, GuardrailConfig } from "@/lib/api";

interface AuditLogsResponse {
  items: AuditLog[];
  total: number;
}

function ToggleSwitch({
  enabled,
  onChange,
  disabled,
}: {
  enabled: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      aria-pressed={enabled}
      style={{
        width: 44,
        height: 24,
        borderRadius: 12,
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: enabled ? "#2563eb" : "#e2e8f0",
        position: "relative",
        transition: "background 0.2s",
        flexShrink: 0,
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "#fff",
          position: "absolute",
          top: 3,
          left: enabled ? 23 : 3,
          transition: "left 0.2s",
          boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
        }}
      />
    </button>
  );
}

const EVENT_COLORS: Record<string, { bg: string; text: string }> = {
  input_blocked: { bg: "#fee2e2", text: "#b91c1c" },
  rate_limited: { bg: "#fef3c7", text: "#92400e" },
  pii_masked: { bg: "#fce7f3", text: "#9d174d" },
  hallucination_flagged: { bg: "#ede9fe", text: "#5b21b6" },
  abuse_warned: { bg: "#ffedd5", text: "#c2410c" },
};

export default function GuardrailsPage() {
  const [config, setConfig] = useState<GuardrailConfig | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(false);
  const [newTopic, setNewTopic] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      const [cfg, logRes] = await Promise.all([
        api.get<GuardrailConfig>("/guardrails/config"),
        api.get<AuditLogsResponse>("/guardrails/audit-logs?limit=20"),
      ]);
      setConfig(cfg);
      setLogs(logRes.items);
      setLogsTotal(logRes.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function toggleHallucinationCheck() {
    if (!config) return;
    setConfigLoading(true);
    try {
      const updated = await api.patch<GuardrailConfig>("/guardrails/config", {
        hallucination_check: {
          ...config.hallucination_check,
          enabled: !config.hallucination_check.enabled,
        },
      });
      setConfig(updated);
    } finally {
      setConfigLoading(false);
    }
  }

  async function toggleToneCheck() {
    if (!config) return;
    setConfigLoading(true);
    try {
      const updated = await api.patch<GuardrailConfig>("/guardrails/config", {
        tone_check: {
          ...config.tone_check,
          enabled: !config.tone_check.enabled,
        },
      });
      setConfig(updated);
    } finally {
      setConfigLoading(false);
    }
  }

  async function addBlockedTopic() {
    if (!config || !newTopic.trim()) return;
    setConfigLoading(true);
    try {
      const updated = await api.patch<GuardrailConfig>("/guardrails/config", {
        blocked_topics: [...config.blocked_topics, newTopic.trim()],
      });
      setConfig(updated);
      setNewTopic("");
    } finally {
      setConfigLoading(false);
    }
  }

  async function removeTopic(topic: string) {
    if (!config) return;
    const updated = await api.patch<GuardrailConfig>("/guardrails/config", {
      blocked_topics: config.blocked_topics.filter((t) => t !== topic),
    });
    setConfig(updated);
  }

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "60px 0",
          color: "#94a3b8",
          gap: 12,
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            border: "3px solid #e2e8f0",
            borderTopColor: "#2563eb",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <span style={{ fontSize: 13 }}>Loading guardrails...</span>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ padding: "28px 32px", minHeight: "100%" }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: 0 }}>
          Guardrails
        </h1>
        <p style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
          Configure AI safety controls and review the audit log.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start" }}>
        {/* ── Left: Config ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Rate Limits */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "14px 20px",
                borderBottom: "1px solid #f1f5f9",
                background: "#f8fafc",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 22,
                  background: "#f59e0b",
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
                </svg>
              </div>
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Rate Limits
              </h2>
            </div>
            <div style={{ padding: "4px 20px 8px" }}>
              {config &&
                Object.entries(config.rate_limits).map(([key, val]) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "11px 0",
                      borderBottom: "1px solid #f1f5f9",
                    }}
                  >
                    <span style={{ fontSize: 13, color: "#64748b" }}>
                      {key.replace(/_/g, " ")}
                    </span>
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: "#0f172a",
                        background: "#f1f5f9",
                        padding: "3px 10px",
                        borderRadius: 6,
                      }}
                    >
                      {val}
                    </span>
                  </div>
                ))}
            </div>
          </div>

          {/* AI Checks */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "14px 20px",
                borderBottom: "1px solid #f1f5f9",
                background: "#f8fafc",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 22,
                  background: "#2563eb",
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                AI Safety Checks
              </h2>
            </div>
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Hallucination */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "14px 16px",
                  background: "#f8fafc",
                  borderRadius: 8,
                  border: "1px solid #f1f5f9",
                }}
              >
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a" }}>
                    Hallucination Check
                  </div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                    Validates numeric claims against evidence. Tolerance:{" "}
                    {config?.hallucination_check.numeric_tolerance_pct ?? "—"}%
                  </div>
                </div>
                <ToggleSwitch
                  enabled={config?.hallucination_check.enabled ?? false}
                  onChange={toggleHallucinationCheck}
                  disabled={configLoading}
                />
              </div>

              {/* Tone check */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "14px 16px",
                  background: "#f8fafc",
                  borderRadius: 8,
                  border: "1px solid #f1f5f9",
                }}
              >
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a" }}>
                    Tone Check
                  </div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                    Enforces respectful, NVC-compliant responses.
                    {config?.tone_check.nvc_strict ? " (Strict)" : ""}
                  </div>
                </div>
                <ToggleSwitch
                  enabled={config?.tone_check.enabled ?? false}
                  onChange={toggleToneCheck}
                  disabled={configLoading}
                />
              </div>
            </div>
          </div>

          {/* Blocked Topics */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "14px 20px",
                borderBottom: "1px solid #f1f5f9",
                background: "#f8fafc",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 22,
                  background: "#ef4444",
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" /><line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                </svg>
              </div>
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Blocked Topics
              </h2>
            </div>
            <div style={{ padding: 20 }}>
              <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
                <input
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addBlockedTopic()}
                  placeholder="Add a blocked topic..."
                  style={{
                    flex: 1,
                    padding: "8px 12px",
                    border: "1px solid #e2e8f0",
                    borderRadius: 8,
                    fontSize: 13,
                    color: "#0f172a",
                    outline: "none",
                    background: "#fafafa",
                  }}
                />
                <button
                  onClick={addBlockedTopic}
                  disabled={configLoading || !newTopic.trim()}
                  style={{
                    padding: "8px 16px",
                    background: "#2563eb",
                    color: "#fff",
                    border: "none",
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    opacity: configLoading || !newTopic.trim() ? 0.6 : 1,
                  }}
                >
                  Add
                </button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {config?.blocked_topics.map((topic) => (
                  <span
                    key={topic}
                    style={{
                      fontSize: 12,
                      padding: "4px 10px 4px 12px",
                      background: "#fee2e2",
                      color: "#b91c1c",
                      borderRadius: 20,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      border: "1px solid #fecaca",
                    }}
                  >
                    {topic}
                    <button
                      onClick={() => removeTopic(topic)}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "#b91c1c",
                        fontSize: 15,
                        lineHeight: 1,
                        padding: 0,
                        display: "flex",
                        alignItems: "center",
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {config?.blocked_topics.length === 0 && (
                  <p style={{ fontSize: 12, color: "#94a3b8", margin: 0 }}>
                    No topics blocked. Add topics the AI should refuse to discuss.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Right: Audit Logs ── */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "14px 20px",
              borderBottom: "1px solid #e2e8f0",
              background: "#f8fafc",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  background: "#0f172a",
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Audit Log
              </h2>
            </div>
            <span style={{ fontSize: 12, color: "#64748b" }}>{logsTotal} events</span>
          </div>

          <div style={{ maxHeight: 540, overflowY: "auto" }}>
            {logs.length === 0 ? (
              <div
                style={{
                  padding: "48px 24px",
                  textAlign: "center",
                  color: "#94a3b8",
                  fontSize: 13,
                }}
              >
                No audit events yet.
              </div>
            ) : (
              logs.map((log, i) => {
                const c = EVENT_COLORS[log.event_type] ?? { bg: "#f3f4f6", text: "#374151" };
                const isLast = i === logs.length - 1;
                return (
                  <div
                    key={log.id}
                    style={{
                      padding: "14px 20px",
                      borderBottom: isLast ? "none" : "1px solid #f1f5f9",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: 8,
                        marginBottom: 6,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 11,
                          padding: "2px 8px",
                          borderRadius: 4,
                          background: c.bg,
                          color: c.text,
                          fontWeight: 600,
                        }}
                      >
                        {log.event_type}
                      </span>
                      <span style={{ fontSize: 11, color: "#94a3b8", flexShrink: 0 }}>
                        {new Date(log.created_at).toLocaleString("en-US", {
                          hour: "2-digit",
                          minute: "2-digit",
                          day: "2-digit",
                          month: "short",
                        })}
                      </span>
                    </div>
                    <p style={{ fontSize: 12, color: "#475569", margin: "0 0 4px" }}>{log.trigger}</p>
                    <p style={{ fontSize: 11, color: "#94a3b8", margin: 0 }}>
                      Action: {log.action_taken}
                    </p>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
