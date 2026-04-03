"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Rule, RuleListResponse } from "@/lib/api";

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

export default function RulesPage() {
  const [data, setData] = useState<RuleListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setData(await api.get<RuleListResponse>("/rules"));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function toggle(rule: Rule) {
    setToggling(rule.id);
    try {
      await api.patch(`/rules/${rule.id}`, { is_enabled: !rule.is_enabled });
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to update rule");
    } finally {
      setToggling(null);
    }
  }

  const TRIGGER_COLORS: Record<string, { bg: string; text: string }> = {
    intent_match: { bg: "#ede9fe", text: "#5b21b6" },
    keyword: { bg: "#e0f2fe", text: "#0369a1" },
    threshold: { bg: "#fef3c7", text: "#92400e" },
    manual: { bg: "#f1f5f9", text: "#475569" },
  };

  return (
    <div style={{ padding: "28px 32px", minHeight: "100%" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 24,
        }}
      >
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: 0 }}>
            Automation Rules
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
            Configure when AI actions are automatically triggered. Toggle rules on or off.
          </p>
        </div>
        <button
          onClick={refresh}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "8px 16px",
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            fontSize: 13,
            color: "#374151",
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Summary chips */}
      {!loading && data && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          <div
            style={{
              background: "#dcfce7",
              border: "1px solid #bbf7d0",
              borderRadius: 8,
              padding: "8px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 15, fontWeight: 700, color: "#166534" }}>
              {data.items.filter((r) => r.is_enabled).length}
            </span>
            <span style={{ fontSize: 12, color: "#166534" }}>Active</span>
          </div>
          <div
            style={{
              background: "#f1f5f9",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "8px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 15, fontWeight: 700, color: "#64748b" }}>
              {data.items.filter((r) => !r.is_enabled).length}
            </span>
            <span style={{ fontSize: 12, color: "#64748b" }}>Inactive</span>
          </div>
          <div
            style={{
              background: "#eff6ff",
              border: "1px solid #bfdbfe",
              borderRadius: 8,
              padding: "8px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 15, fontWeight: 700, color: "#1d4ed8" }}>
              {data.total}
            </span>
            <span style={{ fontSize: 12, color: "#1d4ed8" }}>Total Rules</span>
          </div>
        </div>
      )}

      {/* Rules list */}
      {loading ? (
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
          <span style={{ fontSize: 13 }}>Loading rules...</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : (
        <div
          style={{
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {/* Table header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 120px 160px 80px",
              padding: "10px 20px",
              background: "#f8fafc",
              borderBottom: "1px solid #e2e8f0",
              gap: 12,
            }}
          >
            {["Rule", "Trigger", "Threshold / Intent", "Enabled"].map((h) => (
              <span key={h} style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                {h}
              </span>
            ))}
          </div>

          {data?.items.length === 0 ? (
            <div style={{ padding: "48px 24px", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
              No rules configured yet.
            </div>
          ) : (
            data?.items.map((rule, i) => {
              const triggerStyle = TRIGGER_COLORS[rule.trigger] ?? { bg: "#f1f5f9", text: "#475569" };
              const isLast = i === (data?.items.length ?? 0) - 1;
              return (
                <div
                  key={rule.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 120px 160px 80px",
                    padding: "16px 20px",
                    borderBottom: isLast ? "none" : "1px solid #f1f5f9",
                    alignItems: "center",
                    gap: 12,
                    transition: "background 0.1s",
                    background: rule.is_enabled ? "#fff" : "#fafafa",
                  }}
                >
                  {/* Name + description */}
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>
                        {rule.name}
                      </span>
                      {!rule.is_enabled && (
                        <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, background: "#f1f5f9", color: "#94a3b8", fontWeight: 500 }}>
                          OFF
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>{rule.description}</p>
                  </div>

                  {/* Trigger */}
                  <span
                    style={{
                      fontSize: 11,
                      padding: "3px 9px",
                      borderRadius: 4,
                      background: triggerStyle.bg,
                      color: triggerStyle.text,
                      fontWeight: 500,
                      width: "fit-content",
                    }}
                  >
                    {rule.trigger}
                  </span>

                  {/* Intent / threshold */}
                  <div>
                    <div style={{ fontSize: 12, color: "#475569" }}>
                      <span style={{ color: "#94a3b8" }}>Intent:</span> {rule.intent_key}
                    </div>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                      Threshold: {rule.sensitivity_threshold}
                    </div>
                  </div>

                  {/* Toggle */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <ToggleSwitch
                      enabled={rule.is_enabled}
                      onChange={() => toggle(rule)}
                      disabled={toggling === rule.id}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
