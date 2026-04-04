"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Action, ActionListResponse } from "@/lib/api";

// ── Helpers ─────────────────────────────────────────────────────────────────

function hrRef(id: string) {
  return `HR-2026-${id.slice(0, 4).toUpperCase()}`;
}

function isToday(dateStr: string) {
  const d = new Date(dateStr);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function formatTime(dateStr: string) {
  return new Date(dateStr).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateTime(dateStr: string) {
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actionCategoryKey(action: Action) {
  switch (action.type?.toLowerCase()) {
    case "document_generation":
      return "documents";
    case "leave_request":
      return "leave";
    case "reimbursement_request":
      return "reimbursement";
    case "profile_update_request":
      return "profile";
    case "counseling_task":
    case "escalation":
      return "sensitive";
    case "followup_chat":
      return "followup";
    default:
      return "other";
  }
}

function categoryLabel(action: Action) {
  const map: Record<string, string> = {
    documents: "Documents",
    leave: "Leave",
    reimbursement: "Reimbursement",
    profile: "Profile Update",
    sensitive: "Sensitive",
    followup: "Follow-up",
    other: "Other",
  };
  return map[actionCategoryKey(action)] ?? "Other";
}

function buildDueLabel(action: Action) {
  if (typeof action.sla_hours === "number" && action.sla_hours > 0) {
    const dueAt = new Date(new Date(action.created_at).getTime() + action.sla_hours * 60 * 60 * 1000);
    return `Due ${formatDateTime(dueAt.toISOString())}`;
  }
  return `Created ${formatTime(action.created_at)}`;
}

function priorityRank(priority: string | undefined) {
  switch ((priority ?? "").toLowerCase()) {
    case "urgent":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    case "low":
      return 1;
    default:
      return 0;
  }
}

const PRIORITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  urgent: { bg: "#fecaca", text: "#991b1b", label: "Urgent" },
  high: { bg: "#fee2e2", text: "#b91c1c", label: "High" },
  medium: { bg: "#fef3c7", text: "#92400e", label: "Medium" },
  low: { bg: "#dcfce7", text: "#166534", label: "Low" },
};

const STATUS_BADGE: Record<string, { bg: string; text: string }> = {
  pending: { bg: "#fef3c7", text: "#92400e" },
  ready: { bg: "#dbeafe", text: "#1e40af" },
  in_progress: { bg: "#e0f2fe", text: "#075985" },
  completed: { bg: "#f0fdf4", text: "#166534" },
  failed: { bg: "#fee2e2", text: "#b91c1c" },
  cancelled: { bg: "#f3f4f6", text: "#374151" },
};

const CATEGORY_BADGE: Record<string, { bg: string; text: string }> = {
  documents: { bg: "#ede9fe", text: "#5b21b6" },
  leave: { bg: "#e0f2fe", text: "#0369a1" },
  reimbursement: { bg: "#fef3c7", text: "#92400e" },
  profile: { bg: "#dcfce7", text: "#166534" },
  sensitive: { bg: "#fce7f3", text: "#9d174d" },
  followup: { bg: "#ecfccb", text: "#3f6212" },
  other: { bg: "#f1f5f9", text: "#475569" },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  color,
  icon,
  sub,
}: {
  label: string;
  value: number | string;
  color: string;
  icon: React.ReactNode;
  sub?: string;
}) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 12,
        padding: "20px 22px",
        border: "1px solid #e2e8f0",
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 500, color: "#64748b" }}>{label}</span>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: color + "18",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color,
          }}
        >
          {icon}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 30, fontWeight: 700, color: "#0f172a", lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  );
}

function FilterTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "7px 16px",
        borderRadius: 8,
        border: "none",
        background: active ? "#2563eb" : "transparent",
        color: active ? "#fff" : "#64748b",
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        cursor: "pointer",
        transition: "all 0.15s",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

function ActionCard({ action, onClick }: { action: Action; onClick: () => void }) {
  const priority = PRIORITY_BADGE[action.priority?.toLowerCase()] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.priority ?? "—",
  };
  const categoryKey = actionCategoryKey(action);
  const cat = CATEGORY_BADGE[categoryKey] ?? CATEGORY_BADGE.other;
  const status = STATUS_BADGE[action.status] ?? { bg: "#f3f4f6", text: "#374151" };

  return (
    <div
      onClick={onClick}
      style={{
        background: "#fff",
        border: "1px solid #e2e8f0",
        borderRadius: 12,
        padding: "18px 20px",
        cursor: "pointer",
        transition: "box-shadow 0.15s, border-color 0.15s",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 16px rgba(0,0,0,0.08)";
        (e.currentTarget as HTMLDivElement).style.borderColor = "#bfdbfe";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
        (e.currentTarget as HTMLDivElement).style.borderColor = "#e2e8f0";
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", fontFamily: "monospace" }}>
          {hrRef(action.id)}
        </span>
        <span
          style={{
            fontSize: 11,
            padding: "2px 8px",
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
            padding: "2px 8px",
            borderRadius: 4,
            background: cat.bg,
            color: cat.text,
            fontWeight: 500,
          }}
          >
            {categoryLabel(action)}
          </span>
        <div style={{ flex: 1 }} />
        <span
          style={{
            fontSize: 11,
            padding: "2px 8px",
            borderRadius: 4,
            background: status.bg,
            color: status.text,
            fontWeight: 500,
            textTransform: "capitalize",
          }}
        >
          {action.status?.replace("_", " ")}
        </span>
      </div>

      {/* Title */}
      <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>{action.title}</div>

      {/* Summary */}
      {action.summary && (
        <div style={{ fontSize: 13, color: "#64748b", lineHeight: 1.5 }}>
          {action.summary.slice(0, 110)}
          {action.summary.length > 110 ? "…" : ""}
        </div>
      )}

      {/* Footer row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>
          {buildDueLabel(action)}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClick();
          }}
          style={{
            fontSize: 12,
            padding: "6px 14px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          View Case
        </button>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

const FILTER_TABS = [
  { key: "all", label: "All" },
  { key: "documents", label: "Documents" },
  { key: "leave", label: "Leave" },
  { key: "reimbursement", label: "Reimbursement" },
  { key: "sensitive", label: "Sensitive" },
  { key: "profile", label: "Profile" },
];

export default function HRDashboard() {
  const router = useRouter();
  const [actions, setActions] = useState<ActionListResponse | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .get<ActionListResponse>("/actions")
      .then(setActions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const items = actions?.items ?? [];

  // Stats
  const newToday = items.filter((a) => isToday(a.created_at)).length;
  const pending = items.filter((a) => a.status === "pending" || a.status === "ready").length;
  const highPriority = items.filter((a) => priorityRank(a.priority) >= 3).length;
  const resolved = items.filter((a) => a.status === "completed").length;

  // AI Insights
  const criticalPending = items.filter(
    (a) => priorityRank(a.priority) >= 4 && (a.status === "pending" || a.status === "ready")
  ).length;
  const inProgress = items.filter((a) => a.status === "in_progress").length;
  const topAction = items
    .filter((a) => a.status === "pending" || a.status === "ready")
    .sort((a, b) => {
      const rankDiff = priorityRank(b.priority) - priorityRank(a.priority);
      if (rankDiff !== 0) {
        return rankDiff;
      }
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    })[0];

  // Filter
  const filtered =
    activeFilter === "all"
      ? items.slice(0, 10)
      : items.filter((a) => actionCategoryKey(a) === activeFilter).slice(0, 10);

  return (
    <div style={{ padding: "28px 32px", minHeight: "100%" }}>
      {/* Page Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: 0 }}>
          HR Operations Dashboard
        </h1>
        <p style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
          Manage employee requests and priority actions
        </p>
      </div>

      {/* Stats Row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        <StatCard
          label="New Cases Today"
          value={newToday}
          color="#2563eb"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" /><line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          }
          sub="Since midnight"
        />
        <StatCard
          label="Pending Actions"
          value={pending}
          color="#f59e0b"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
          }
          sub="Awaiting review"
        />
        <StatCard
          label="High Priority"
          value={highPriority}
          color="#ef4444"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          }
          sub="Needs attention"
        />
        <StatCard
          label="AI Resolved"
          value={resolved}
          color="#10b981"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          }
          sub="Completed cases"
        />
      </div>

      {/* AI Insights Card */}
      <div
        style={{
          background: "#eff6ff",
          border: "1px solid #bfdbfe",
          borderRadius: 12,
          padding: "20px 24px",
          marginBottom: 24,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              width: 28,
              height: 28,
              background: "#2563eb",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
          </div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#1e3a8a", margin: 0 }}>
            AI Insights &amp; Recommendations
          </h2>
        </div>

        {/* Metrics */}
        <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
          <div
            style={{
              background: "#fee2e2",
              border: "1px solid #fecaca",
              borderRadius: 8,
              padding: "8px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 700, color: "#b91c1c" }}>{criticalPending}</span>
            <span style={{ fontSize: 12, color: "#b91c1c" }}>Critical Priority</span>
          </div>
          <div
            style={{
              background: "#fef3c7",
              border: "1px solid #fde68a",
              borderRadius: 8,
              padding: "8px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 700, color: "#92400e" }}>{inProgress}</span>
            <span style={{ fontSize: 12, color: "#92400e" }}>Needs Escalation</span>
          </div>
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
            <span style={{ fontSize: 16, fontWeight: 700, color: "#166534" }}>{resolved}</span>
            <span style={{ fontSize: 12, color: "#166534" }}>On Track</span>
          </div>
        </div>

        {/* Recommended action */}
        {topAction ? (
          <div
            style={{
              background: "#fff",
              border: "1px solid #dbeafe",
              borderRadius: 8,
              padding: "14px 16px",
              display: "flex",
              alignItems: "flex-start",
              gap: 14,
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "#ef4444",
                marginTop: 5,
                flexShrink: 0,
              }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 3 }}>
                Recommended First Action
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a" }}>{topAction.title}</div>
              {topAction.summary && (
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 3 }}>
                  {topAction.summary.slice(0, 100)}…
                </div>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button
                onClick={() => router.push(`/hr/actions/${topAction.id}`)}
                style={{
                  fontSize: 12,
                  padding: "7px 16px",
                  background: "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                }}
              >
                View Case
              </button>
              <button
                onClick={() => router.push("/hr/actions")}
                style={{
                  fontSize: 12,
                  padding: "7px 12px",
                  background: "transparent",
                  color: "#2563eb",
                  border: "none",
                  cursor: "pointer",
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                }}
              >
                Show All →
              </button>
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "#64748b" }}>No high-priority pending actions. All clear.</div>
        )}
      </div>

      {/* Action List */}
      <div
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #f1f5f9",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>
            Today&apos;s Action List
          </h2>
          <span style={{ fontSize: 12, color: "#94a3b8" }}>
            Showing {filtered.length} of {items.length}
          </span>
        </div>

        {/* Filter Tabs */}
        <div
          style={{
            padding: "10px 20px",
            borderBottom: "1px solid #f1f5f9",
            display: "flex",
            gap: 4,
            background: "#f8fafc",
          }}
        >
          {FILTER_TABS.map((tab) => (
            <FilterTab
              key={tab.key}
              label={tab.label}
              active={activeFilter === tab.key}
              onClick={() => setActiveFilter(tab.key)}
            />
          ))}
        </div>

        {/* Cards */}
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          {loading ? (
            <div style={{ padding: "32px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
              Loading cases...
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: "32px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
              No actions in this category.
            </div>
          ) : (
            filtered.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                onClick={() => router.push(`/hr/actions/${action.id}`)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
