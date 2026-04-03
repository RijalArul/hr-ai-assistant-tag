"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Action, ActionListResponse } from "@/lib/api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function hrRef(id: string) {
  return `HR-2026-${id.slice(0, 4).toUpperCase()}`;
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function categoryLabel(type: string) {
  const map: Record<string, string> = {
    complaint: "Complaints",
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

const STATUS_BADGE: Record<string, { bg: string; text: string }> = {
  pending: { bg: "#fef3c7", text: "#92400e" },
  ready: { bg: "#dbeafe", text: "#1e40af" },
  in_progress: { bg: "#e0f2fe", text: "#075985" },
  completed: { bg: "#f0fdf4", text: "#166534" },
  failed: { bg: "#fee2e2", text: "#b91c1c" },
  cancelled: { bg: "#f3f4f6", text: "#374151" },
};

const CATEGORY_BADGE: Record<string, { bg: string; text: string }> = {
  complaint: { bg: "#fce7f3", text: "#9d174d" },
  payroll: { bg: "#ede9fe", text: "#5b21b6" },
  leave: { bg: "#e0f2fe", text: "#0369a1" },
  reimbursement: { bg: "#fef3c7", text: "#92400e" },
};

const FILTER_TABS = [
  { key: "all", label: "All" },
  { key: "complaint", label: "Complaints" },
  { key: "payroll", label: "Payroll" },
  { key: "leave", label: "Leave" },
  { key: "reimbursement", label: "Reimbursement" },
];

// ── ActionCard ────────────────────────────────────────────────────────────────

function ActionCard({ action, onClick }: { action: Action; onClick: () => void }) {
  const priority = PRIORITY_BADGE[action.sensitivity?.toLowerCase()] ?? {
    bg: "#f3f4f6",
    text: "#374151",
    label: action.sensitivity ?? "—",
  };
  const cat = CATEGORY_BADGE[action.type?.toLowerCase()] ?? { bg: "#f1f5f9", text: "#475569" };
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
          {categoryLabel(action.type)}
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
          {action.summary.slice(0, 120)}
          {action.summary.length > 120 ? "…" : ""}
        </div>
      )}

      {/* Footer */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>{formatDate(action.created_at)}</span>
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
          Open Case
        </button>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ActionsPage() {
  const router = useRouter();
  const [data, setData] = useState<ActionListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState("all");

  async function refresh() {
    setLoading(true);
    try {
      const res = await api.get<ActionListResponse>("/actions");
      setData(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const items = data?.items ?? [];
  const filtered =
    activeFilter === "all"
      ? items
      : items.filter((a) => a.type?.toLowerCase() === activeFilter);

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
            Case Queue
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
            {data?.total ?? 0} total cases · {filtered.length} shown
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
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "#f8fafc";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "#fff";
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Filter Tabs */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 20,
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 10,
          padding: 6,
          width: "fit-content",
        }}
      >
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveFilter(tab.key)}
            style={{
              padding: "7px 16px",
              borderRadius: 7,
              border: "none",
              background: activeFilter === tab.key ? "#2563eb" : "transparent",
              color: activeFilter === tab.key ? "#fff" : "#64748b",
              fontSize: 13,
              fontWeight: activeFilter === tab.key ? 600 : 400,
              cursor: "pointer",
              transition: "all 0.15s",
              whiteSpace: "nowrap",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Cards */}
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
          <span style={{ fontSize: 13 }}>Loading cases...</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : filtered.length === 0 ? (
        <div
          style={{
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            padding: "48px 24px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 12 }}>📋</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", marginBottom: 4 }}>
            No cases found
          </div>
          <div style={{ fontSize: 13, color: "#94a3b8" }}>
            No actions in the {activeFilter === "all" ? "queue" : activeFilter} category.
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {filtered.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              onClick={() => router.push(`/hr/actions/${action.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
