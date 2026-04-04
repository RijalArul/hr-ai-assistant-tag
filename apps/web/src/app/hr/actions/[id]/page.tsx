"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Action, ActionExecutionResponse } from "@/lib/api";

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

function titleize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function computeDueAt(action: Action) {
  if (typeof action.sla_hours !== "number" || action.sla_hours <= 0) {
    return null;
  }
  return new Date(new Date(action.created_at).getTime() + action.sla_hours * 60 * 60 * 1000);
}

function stringifyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function getMissingPayloadFields(payload?: Record<string, unknown>) {
  if (!payload || Array.isArray(payload)) {
    return [];
  }

  const optionalEmptyKeys = new Set([
    "type",
    "note",
    "reason",
    "description",
    "delivery_note",
    "template_key",
    "parameters",
    "target_reference",
    "payload_template",
    "scheduled_at",
    "due_at",
  ]);

  return Object.entries(payload)
    .filter(([key, value]) => {
      if (optionalEmptyKeys.has(key)) {
        return false;
      }
      if (value === null) {
        return true;
      }
      if (typeof value === "string") {
        return value.trim().length === 0;
      }
      if (Array.isArray(value)) {
        return value.length === 0;
      }
      if (typeof value === "object") {
        return Object.keys(value as Record<string, unknown>).length === 0;
      }
      return false;
    })
    .map(([key]) => titleize(key));
}

const PRIORITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  urgent: { bg: "#fecaca", text: "#991b1b", label: "Urgent" },
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

const SENSITIVITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: "#fce7f3", text: "#9d174d", label: "High" },
  medium: { bg: "#fff7ed", text: "#c2410c", label: "Medium" },
  low: { bg: "#eff6ff", text: "#1d4ed8", label: "Low" },
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: 16,
        padding: "11px 0",
        borderBottom: "1px solid #f1f5f9",
      }}
    >
      <span style={{ fontSize: 13, color: "#64748b", fontWeight: 500 }}>{label}</span>
      <span style={{ fontSize: 13, color: "#0f172a", fontWeight: 500, textAlign: "right" }}>
        {value}
      </span>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
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
        <h2 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

export default function CaseDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [action, setAction] = useState<Action | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      return;
    }

    setLoading(true);
    api
      .get<Action>(`/actions/${id}`)
      .then((result) => {
        setAction(result);
        setError(null);
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Failed to load case.");
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function updateStatus(status: "in_progress" | "cancelled") {
    if (!action) {
      return;
    }

    setUpdating(true);
    try {
      const updated = await api.patch<Action>(`/actions/${id}`, { status });
      setAction(updated);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update status.");
    } finally {
      setUpdating(false);
    }
  }

  async function executeCurrentAction() {
    if (!action) {
      return;
    }

    setUpdating(true);
    try {
      const execution = await api.post<ActionExecutionResponse>(`/actions/${id}/execute`, {
        trigger_delivery: true,
        executor_note: "Completed from HR Operations dashboard.",
      });
      setAction(execution.action);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to execute action.");
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
          onClick={() => router.push("/hr/actions")}
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
          Back to Queue
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

  const priority = PRIORITY_BADGE[action.priority?.toLowerCase()] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.priority ?? "Unknown",
  };
  const status = STATUS_BADGE[action.status] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.status,
  };
  const sensitivity = SENSITIVITY_BADGE[action.sensitivity?.toLowerCase()] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.sensitivity ?? "Unknown",
  };
  const dueAt = computeDueAt(action);
  const missingPayloadFields = getMissingPayloadFields(action.payload);
  const isCompleted = action.status === "completed";
  const isCancelled = action.status === "cancelled";
  const isFailed = action.status === "failed";
  const canMarkInProgress = !updating && !isCompleted && !isCancelled && !isFailed && action.status !== "in_progress";
  const canCancel = !updating && !isCompleted && !isCancelled && !isFailed;
  const canExecute = !updating && !isCompleted && !isCancelled && !isFailed;

  return (
    <div style={{ padding: "28px 32px", minHeight: "100%" }}>
      <button
        onClick={() => router.push("/hr/actions")}
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
        Back to Queue
      </button>

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
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#2563eb",
              fontFamily: "monospace",
              marginBottom: 4,
            }}
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
                background: sensitivity.bg,
                color: sensitivity.text,
                fontWeight: 600,
              }}
            >
              {sensitivity.label} Sensitivity
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

        <div style={{ display: "flex", gap: 10, flexShrink: 0, flexWrap: "wrap", alignItems: "center" }}>
          {action.suggested_pic ? (
            <div
              style={{
                padding: "9px 14px",
                border: "1px solid #bfdbfe",
                borderRadius: 8,
                background: "#eff6ff",
                color: "#1d4ed8",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              Suggested PIC: {action.suggested_pic}
            </div>
          ) : null}
          <button
            onClick={() => updateStatus("in_progress")}
            disabled={!canMarkInProgress}
            style={{
              padding: "9px 18px",
              border: "1px solid #0369a1",
              borderRadius: 8,
              background: action.status === "in_progress" ? "#e0f2fe" : "#fff",
              color: "#0369a1",
              fontSize: 13,
              fontWeight: 600,
              cursor: canMarkInProgress ? "pointer" : "not-allowed",
              opacity: canMarkInProgress ? 1 : 0.6,
            }}
          >
            {action.status === "in_progress" ? "Review Claimed" : "Mark In Progress"}
          </button>
          <button
            onClick={executeCurrentAction}
            disabled={!canExecute}
            style={{
              padding: "9px 18px",
              border: "none",
              borderRadius: 8,
              background: isCompleted ? "#bbf7d0" : "#16a34a",
              color: isCompleted ? "#166534" : "#fff",
              fontSize: 13,
              fontWeight: 600,
              cursor: canExecute ? "pointer" : "not-allowed",
              opacity: canExecute ? 1 : 0.7,
            }}
          >
            {isCompleted ? "Completed" : "Complete Case"}
          </button>
          <button
            onClick={() => updateStatus("cancelled")}
            disabled={!canCancel}
            style={{
              padding: "9px 18px",
              border: "1px solid #64748b",
              borderRadius: 8,
              background: isCancelled ? "#f1f5f9" : "#fff",
              color: "#475569",
              fontSize: 13,
              fontWeight: 600,
              cursor: canCancel ? "pointer" : "not-allowed",
              opacity: canCancel ? 1 : 0.7,
            }}
          >
            {isCancelled ? "Cancelled" : "Cancel Case"}
          </button>
        </div>
      </div>

      {error ? (
        <div
          style={{
            marginBottom: 16,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#b91c1c",
            borderRadius: 10,
            padding: "12px 14px",
            fontSize: 13,
          }}
        >
          {error}
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          <Card title="Case Information">
            <div style={{ padding: "4px 20px 12px" }}>
              <InfoRow label="Action Type" value={titleize(action.type ?? "unknown")} />
              <InfoRow label="Priority" value={priority.label} />
              <InfoRow label="Sensitivity" value={sensitivity.label} />
              <InfoRow label="Status" value={status.label} />
              <InfoRow label="Delivery Channels" value={action.delivery_channels.join(", ") || "None"} />
              <InfoRow label="SLA" value={action.sla_hours ? `${action.sla_hours} hours` : "Not set"} />
              <InfoRow label="Due At" value={dueAt ? formatDateTime(dueAt.toISOString()) : "Not set"} />
            </div>
          </Card>

          <Card title="AI-Generated Summary">
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
          </Card>

          <Card title="Structured Payload">
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
              {missingPayloadFields.length > 0 ? (
                <div
                  style={{
                    background: "#fff7ed",
                    border: "1px solid #fed7aa",
                    borderRadius: 10,
                    padding: "12px 14px",
                    fontSize: 13,
                    color: "#9a3412",
                  }}
                >
                  Missing information still visible in payload: {missingPayloadFields.join(", ")}.
                </div>
              ) : null}
              <pre
                style={{
                  margin: 0,
                  padding: 16,
                  borderRadius: 10,
                  background: "#0f172a",
                  color: "#e2e8f0",
                  fontSize: 12,
                  lineHeight: 1.6,
                  overflowX: "auto",
                }}
              >
                {stringifyJson(action.payload)}
              </pre>
            </div>
          </Card>

          {action.execution_result ? (
            <Card title="Execution Result">
              <div style={{ padding: 20 }}>
                <pre
                  style={{
                    margin: 0,
                    padding: 16,
                    borderRadius: 10,
                    background: "#0f172a",
                    color: "#e2e8f0",
                    fontSize: 12,
                    lineHeight: 1.6,
                    overflowX: "auto",
                  }}
                >
                  {stringifyJson(action.execution_result)}
                </pre>
              </div>
            </Card>
          ) : null}
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16, minWidth: 280 }}>
          <Card title="Operational Guidance">
            <div style={{ padding: "4px 20px 12px" }}>
              <InfoRow label="Suggested PIC" value={action.suggested_pic ?? "Not set"} />
              <InfoRow
                label="Suggested Next Action"
                value={action.suggested_next_action ?? "Not set"}
              />
              <InfoRow label="Escalation Rule" value={action.escalation_rule ?? "Not set"} />
            </div>
          </Card>

          <Card title="Case Timeline">
            <div style={{ padding: "4px 20px 12px" }}>
              <InfoRow
                label="Case ID"
                value={<span style={{ fontFamily: "monospace", fontSize: 12 }}>{id}</span>}
              />
              <InfoRow label="Created" value={formatDateTime(action.created_at)} />
              <InfoRow label="Updated" value={formatDateTime(action.updated_at)} />
              <InfoRow
                label="Last Executed"
                value={action.last_executed_at ? formatDateTime(action.last_executed_at) : "Not executed"}
              />
            </div>
          </Card>

          <Card title="Action Notes">
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10 }}>
              <div
                style={{
                  background: "#f8fafc",
                  border: "1px solid #e2e8f0",
                  borderRadius: 10,
                  padding: "12px 14px",
                  fontSize: 13,
                  color: "#475569",
                  lineHeight: 1.6,
                }}
              >
                Manual non-terminal updates stay on the `PATCH /actions/{id}` path, while completion follows the execution path so delivery metadata and execution logs stay consistent.
              </div>
              {action.status === "in_progress" ? (
                <div
                  style={{
                    background: "#e0f2fe",
                    border: "1px solid #bae6fd",
                    borderRadius: 10,
                    padding: "12px 14px",
                    fontSize: 13,
                    color: "#075985",
                    lineHeight: 1.6,
                  }}
                >
                  This case is already claimed for review. You can complete it from here when the follow-up is ready.
                </div>
              ) : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
