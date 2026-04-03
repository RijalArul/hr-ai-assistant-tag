"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Action } from "@/lib/api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function hrRef(id: string) {
  return `HR-2026-${id.slice(0, 4).toUpperCase()}`;
}

function formatDateTime(dateStr: string) {
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function categoryLabel(type: string) {
  const map: Record<string, string> = {
    complaint: "Complaint",
    payroll: "Payroll",
    leave: "Leave",
    reimbursement: "Reimbursement",
  };
  return map[type?.toLowerCase()] ?? type ?? "General";
}

const PRIORITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: "#fee2e2", text: "#b91c1c", label: "High" },
  medium: { bg: "#fef3c7", text: "#92400e", label: "Medium" },
  low: { bg: "#dcfce7", text: "#166534", label: "Low" },
};

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: "#fef3c7", text: "#92400e", label: "Pending" },
  ready: { bg: "#dbeafe", text: "#1e40af", label: "Ready" },
  in_progress: { bg: "#e0f2fe", text: "#075985", label: "In Progress" },
  completed: { bg: "#f0fdf4", text: "#166534", label: "Completed" },
  failed: { bg: "#fee2e2", text: "#b91c1c", label: "Failed" },
  cancelled: { bg: "#f3f4f6", text: "#374151", label: "Cancelled" },
};

// ── InfoRow ───────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "11px 0",
        borderBottom: "1px solid #f1f5f9",
      }}
    >
      <span style={{ fontSize: 13, color: "#64748b", fontWeight: 500 }}>{label}</span>
      <span style={{ fontSize: 13, color: "#0f172a", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CaseDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [action, setAction] = useState<Action | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api
      .get<Action>(`/actions/${id}`)
      .then(setAction)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function updateStatus(status: string) {
    if (!action) return;
    setUpdating(true);
    try {
      const updated = await api.patch<Action>(`/actions/${id}`, { status });
      setAction(updated);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setUpdating(false);
    }
  }

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          gap: 12,
          padding: 60,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            border: "3px solid #e2e8f0",
            borderTopColor: "#2563eb",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <span style={{ fontSize: 13, color: "#94a3b8" }}>Loading case...</span>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error || !action) {
    return (
      <div style={{ padding: "28px 32px" }}>
        <button
          onClick={() => router.push("/hr")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            background: "none",
            border: "none",
            fontSize: 13,
            color: "#2563eb",
            cursor: "pointer",
            padding: 0,
            marginBottom: 24,
            fontWeight: 500,
          }}
        >
          ← Back to Dashboard
        </button>
        <div
          style={{
            background: "#fee2e2",
            border: "1px solid #fecaca",
            borderRadius: 12,
            padding: 24,
            color: "#b91c1c",
            fontSize: 14,
          }}
        >
          {error ?? "Case not found."}
        </div>
      </div>
    );
  }

  const priority = PRIORITY_BADGE[action.sensitivity?.toLowerCase()] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.sensitivity ?? "Unknown",
  };
  const status = STATUS_BADGE[action.status] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.status,
  };

  return (
    <div style={{ padding: "28px 32px", minHeight: "100%" }}>
      {/* Back */}
      <button
        onClick={() => router.push("/hr")}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: "none",
          border: "none",
          fontSize: 13,
          color: "#2563eb",
          cursor: "pointer",
          padding: 0,
          marginBottom: 20,
          fontWeight: 500,
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to Dashboard
      </button>

      {/* Case title row */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 24,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", fontFamily: "monospace", marginBottom: 4 }}
          >
            Case {hrRef(id)}
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", margin: 0 }}>
            {action.title}
          </h1>
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <span
              style={{
                fontSize: 11,
                padding: "3px 9px",
                borderRadius: 4,
                background: priority.bg,
                color: priority.text,
                fontWeight: 600,
              }}
            >
              {priority.label} Priority
            </span>
            <span
              style={{
                fontSize: 11,
                padding: "3px 9px",
                borderRadius: 4,
                background: status.bg,
                color: status.text,
                fontWeight: 500,
              }}
            >
              {status.label}
            </span>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, flexShrink: 0, flexWrap: "wrap" }}>
          <button
            style={{
              padding: "9px 18px",
              border: "1px solid #2563eb",
              borderRadius: 8,
              background: "#fff",
              color: "#2563eb",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Assign Owner
          </button>
          <button
            onClick={() => updateStatus("completed")}
            disabled={updating || action.status === "completed"}
            style={{
              padding: "9px 18px",
              border: "none",
              borderRadius: 8,
              background:
                action.status === "completed" ? "#bbf7d0" : "#16a34a",
              color: action.status === "completed" ? "#166534" : "#fff",
              fontSize: 13,
              fontWeight: 600,
              cursor: action.status === "completed" ? "not-allowed" : "pointer",
              opacity: updating ? 0.7 : 1,
            }}
          >
            {action.status === "completed" ? "Resolved" : "Resolve Case"}
          </button>
        </div>
      </div>

      {/* Two-column layout */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* Left column (2/3) */}
        <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          {/* Case Information */}
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
              }}
            >
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Case Information
              </h2>
            </div>
            <div style={{ padding: "4px 20px 12px" }}>
              <InfoRow
                label="Category"
                value={
                  <span
                    style={{
                      fontSize: 12,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: "#f1f5f9",
                      color: "#334155",
                    }}
                  >
                    {categoryLabel(action.type)}
                  </span>
                }
              />
              <InfoRow
                label="Priority"
                value={
                  <span
                    style={{
                      fontSize: 12,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: priority.bg,
                      color: priority.text,
                      fontWeight: 600,
                    }}
                  >
                    {priority.label}
                  </span>
                }
              />
              <InfoRow
                label="Status"
                value={
                  <span
                    style={{
                      fontSize: 12,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: status.bg,
                      color: status.text,
                      fontWeight: 500,
                    }}
                  >
                    {status.label}
                  </span>
                }
              />
              <InfoRow label="Type" value={action.type ?? "—"} />
              <InfoRow label="Sensitivity" value={action.sensitivity ?? "—"} />
            </div>
          </div>

          {/* AI Summary */}
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
                  <polygon points="12 2 2 7 12 12 22 7 12 2" />
                  <polyline points="2 17 12 22 22 17" />
                  <polyline points="2 12 12 17 22 12" />
                </svg>
              </div>
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                AI-Generated Summary
              </h2>
            </div>
            <div style={{ padding: 20 }}>
              {action.summary ? (
                <p
                  style={{
                    fontSize: 14,
                    color: "#374151",
                    lineHeight: 1.7,
                    margin: 0,
                  }}
                >
                  {action.summary}
                </p>
              ) : (
                <p style={{ fontSize: 14, color: "#94a3b8", margin: 0 }}>
                  No AI summary available for this case.
                </p>
              )}
            </div>
          </div>

          {/* Quick Actions */}
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
              }}
            >
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Quick Actions
              </h2>
            </div>
            <div style={{ padding: 20, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                onClick={() => updateStatus("in_progress")}
                disabled={updating || action.status === "in_progress"}
                style={{
                  padding: "9px 18px",
                  border: "1px solid #0369a1",
                  borderRadius: 8,
                  background: action.status === "in_progress" ? "#e0f2fe" : "#fff",
                  color: "#0369a1",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor:
                    updating || action.status === "in_progress" ? "not-allowed" : "pointer",
                  opacity: updating ? 0.7 : 1,
                }}
              >
                Mark In Progress
              </button>
              <button
                onClick={() => updateStatus("completed")}
                disabled={updating || action.status === "completed"}
                style={{
                  padding: "9px 18px",
                  border: "1px solid #16a34a",
                  borderRadius: 8,
                  background: action.status === "completed" ? "#dcfce7" : "#fff",
                  color: "#16a34a",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor:
                    updating || action.status === "completed" ? "not-allowed" : "pointer",
                  opacity: updating ? 0.7 : 1,
                }}
              >
                Mark Complete
              </button>
              <button
                onClick={() => updateStatus("failed")}
                disabled={updating || action.status === "failed"}
                style={{
                  padding: "9px 18px",
                  border: "1px solid #b91c1c",
                  borderRadius: 8,
                  background: action.status === "failed" ? "#fee2e2" : "#fff",
                  color: "#b91c1c",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor:
                    updating || action.status === "failed" ? "not-allowed" : "pointer",
                  opacity: updating ? 0.7 : 1,
                }}
              >
                Mark Failed
              </button>
            </div>
          </div>
        </div>

        {/* Right column (1/3) */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          {/* Case Metadata */}
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
              }}
            >
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Case Metadata
              </h2>
            </div>
            <div style={{ padding: "4px 20px 12px" }}>
              <InfoRow label="Case ID" value={<span style={{ fontFamily: "monospace", fontSize: 12 }}>{id.slice(0, 8)}…</span>} />
              <InfoRow label="Created" value={formatDateTime(action.created_at)} />
              <InfoRow label="Updated" value={formatDateTime(action.updated_at)} />
              <InfoRow label="Type" value={action.type ?? "—"} />
              <InfoRow
                label="Sensitivity"
                value={
                  <span
                    style={{
                      fontSize: 12,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: priority.bg,
                      color: priority.text,
                      fontWeight: 600,
                      textTransform: "capitalize",
                    }}
                  >
                    {action.sensitivity ?? "—"}
                  </span>
                }
              />
              {action.delivery_channels?.length > 0 && (
                <InfoRow
                  label="Channels"
                  value={action.delivery_channels.join(", ")}
                />
              )}
            </div>
          </div>

          {/* Quick Actions (sidebar copy) */}
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
              }}
            >
              <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Update Status
              </h2>
            </div>
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { status: "in_progress", label: "Mark In Progress", color: "#0369a1", activeBg: "#e0f2fe" },
                { status: "completed", label: "Mark Complete", color: "#16a34a", activeBg: "#dcfce7" },
                { status: "cancelled", label: "Cancel Case", color: "#6b7280", activeBg: "#f3f4f6" },
                { status: "failed", label: "Mark Failed", color: "#b91c1c", activeBg: "#fee2e2" },
              ].map(({ status: s, label, color, activeBg }) => (
                <button
                  key={s}
                  onClick={() => updateStatus(s)}
                  disabled={updating || action.status === s}
                  style={{
                    width: "100%",
                    padding: "9px 14px",
                    border: `1px solid ${color}30`,
                    borderRadius: 8,
                    background: action.status === s ? activeBg : "#fafafa",
                    color,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: updating || action.status === s ? "not-allowed" : "pointer",
                    opacity: updating ? 0.7 : 1,
                    textAlign: "left",
                    transition: "background 0.15s",
                  }}
                >
                  {label}
                  {action.status === s && (
                    <span style={{ fontSize: 11, marginLeft: 6, fontWeight: 400 }}>✓ Current</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
