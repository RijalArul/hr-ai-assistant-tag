// Empty string = same origin; Next.js rewrites /api/v1/* → backend
const API_BASE = "";

function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)hr_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function setToken(token: string): void {
  document.cookie = `hr_token=${encodeURIComponent(token)}; path=/; SameSite=Strict`;
}

export function clearToken(): void {
  document.cookie = "hr_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/chat/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Session {
  employee_id: string;
  company_id: string;
  email: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  session: Session;
}

export interface Action {
  id: string;
  type: string;
  title: string;
  summary: string | null;
  status: string;
  priority: string;
  sensitivity: string;
  delivery_channels: string[];
  suggested_pic?: string | null;
  suggested_next_action?: string | null;
  sla_hours?: number | null;
  escalation_rule?: string | null;
  payload?: Record<string, unknown>;
  execution_result?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
  last_executed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActionListResponse {
  items: Action[];
  total: number;
}

export interface ActionExecutionResponse {
  action: Action;
  delivery_channels: string[];
  delivery_requested: boolean;
  execution_log?: {
    id: string;
    event_name: string;
    status: string;
    message?: string | null;
    metadata?: Record<string, unknown>;
    created_at: string;
  } | null;
  delivery_requests: Array<{
    id: string;
    action_id: string;
    channel: string;
    delivery_status: string;
    target_reference?: string | null;
    payload: Record<string, unknown>;
    created_at: string;
  }>;
  webhook_deliveries_queued: number;
}

export interface Rule {
  id: string;
  name: string;
  description: string;
  trigger: string;
  intent_key: string;
  sensitivity_threshold: string;
  is_enabled: boolean;
  created_at: string;
}

export interface RuleListResponse {
  items: Rule[];
  total: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  attachments: unknown[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Conversation {
  id: string;
  company_id: string;
  employee_id: string;
  title: string | null;
  status: string;
  metadata: Record<string, unknown>;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface ConversationExchangeResponse {
  conversation: Conversation;
  user_message: Message;
  assistant_message: Message;
  triggered_actions: Action[];
}

export interface AuditLog {
  id: string;
  event_type: string;
  trigger: string;
  action_taken: string;
  employee_id: string;
  created_at: string;
}

export interface GuardrailConfig {
  company_id: string;
  rate_limits: {
    messages_per_hour: number;
    conversations_per_day: number;
    file_uploads_per_hour: number;
  };
  blocked_topics: string[];
  hallucination_check: { enabled: boolean; numeric_tolerance_pct: number };
  tone_check: { enabled: boolean; nvc_strict: boolean };
  audit_level: string;
  updated_at: string | null;
}
