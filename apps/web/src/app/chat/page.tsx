"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "@/lib/api";
import type {
  Conversation,
  ConversationExchangeResponse,
  Message,
  MessageAttachment,
  Session,
} from "@/lib/api";

const BLUE = "#2563eb";
const BLUE_DARK = "#1d4ed8";
const BLUE_LIGHT = "#eff6ff";

const SUGGESTIONS = [
  "Kenapa gaji saya lebih rendah bulan ini?",
  "Kapan saldo cuti saya bertambah?",
  "Kapan reimbursement saya cair?",
  "Saya ingin melaporkan masalah sensitif",
];

function initials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
}

function getFirstName(email: string): string {
  const local = email.split("@")[0];
  return local.split(/[._]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

function isGeneratedDocumentAttachment(attachment: MessageAttachment): boolean {
  return (
    attachment.type === "generated_document" ||
    typeof attachment.download_url === "string"
  );
}

function getGeneratedDocumentAttachments(msg: Message): MessageAttachment[] {
  return msg.attachments.filter(isGeneratedDocumentAttachment);
}

function getUrlFileName(url: string): string {
  try {
    const pathname = new URL(url).pathname;
    const raw = pathname.split("/").pop() ?? "document";
    // Strip query-like parts that sometimes end up in pathname
    const name = raw.split("?")[0];
    // Decode percent-encoding and truncate if too long
    const decoded = decodeURIComponent(name);
    return decoded.length > 40 ? decoded.slice(0, 37) + "…" : decoded;
  } catch {
    return "document";
  }
}

function InlineLinkCard({ url, index }: { url: string; index: number }) {
  const isPdf = /\.pdf/i.test(url);
  const fileName = getUrlFileName(url);
  return (
    <a
      key={`link-${index}`}
      href={url}
      target="_blank"
      rel="noreferrer"
      style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        background: "#eff6ff", border: `1px solid #bfdbfe`,
        borderRadius: 8, padding: "6px 10px", marginTop: 6,
        textDecoration: "none", color: "#1e40af",
        fontSize: 12, fontWeight: 500, maxWidth: "100%",
        verticalAlign: "middle",
      }}
    >
      {isPdf ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={BLUE} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      )}
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 240 }}>
        {fileName}
      </span>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0, opacity: 0.6 }}>
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
      </svg>
    </a>
  );
}

function renderMessageContent(content: string): React.ReactNode {
  return content.split(/(https?:\/\/[^\s]+)/g).map((part, index) => {
    if (/^https?:\/\/[^\s]+$/.test(part)) {
      return <InlineLinkCard key={`link-${index}`} url={part} index={index} />;
    }
    return <span key={`text-${index}`}>{part}</span>;
  });
}

// ─── Avatars ───────────────────────────────────────────────────────────────
function UserAvatar({ label }: { label: string }) {
  return (
    <div style={{
      width: 34, height: 34, borderRadius: "50%", background: BLUE,
      color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 12, fontWeight: 700, flexShrink: 0, letterSpacing: 0.5,
    }}>{label}</div>
  );
}

function BotAvatar() {
  return (
    <div style={{
      width: 34, height: 34, borderRadius: "50%",
      background: `linear-gradient(135deg, ${BLUE}, ${BLUE_DARK})`,
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
    }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="8" width="18" height="13" rx="3" stroke="white" strokeWidth="1.8" />
        <path d="M8 8V6a4 4 0 0 1 8 0v2" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="9" cy="14" r="1.2" fill="white" />
        <circle cx="15" cy="14" r="1.2" fill="white" />
        <path d="M9 18h6" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  );
}

// ─── Contextual detection ──────────────────────────────────────────────────
type ModalType = "payslip" | "leave" | "report" | null;

const PAYSLIP_KEYS = ["gaji", "payslip", "slip", "payroll", "salary", "penghasilan", "tunjangan", "potongan", "net pay", "gross", "disburs"];
const LEAVE_KEYS   = ["cuti", "leave", "izin", "absen", "libur", "time off", "saldo cuti", "hari off", "accrual", "annual leave", "sick leave", "jatah"];
const REPORT_KEYS  = ["laporan", "laporkan", "complaint", "masalah", "keluhan", "pelecehan", "harassment", "tidak nyaman", "sensitif", "konfidensial", "report", "aduan"];

function detectActions(text: string): { modal: ModalType; label: string; primary: boolean }[] {
  const t = text.toLowerCase();
  const result: { modal: ModalType; label: string; primary: boolean }[] = [];
  if (PAYSLIP_KEYS.some((k) => t.includes(k)))
    result.push({ modal: "payslip", label: "Lihat Payslip", primary: true });
  if (LEAVE_KEYS.some((k) => t.includes(k)))
    result.push({ modal: "leave", label: "Detail Cuti", primary: result.length === 0 });
  if (REPORT_KEYS.some((k) => t.includes(k)))
    result.push({ modal: "report", label: "Buat Laporan", primary: false });
  return result;
}

function detectQuickReplies(text: string): string[] {
  const t = text.toLowerCase();
  if (PAYSLIP_KEYS.some((k) => t.includes(k)))
    return ["Tunjangan apa saja yang termasuk?", "Kapan gaji bulan ini dibayarkan?"];
  if (LEAVE_KEYS.some((k) => t.includes(k)))
    return ["Bagaimana cara mengajukan cuti?", "Berapa total cuti yang tersisa?"];
  if (REPORT_KEYS.some((k) => t.includes(k)))
    return ["Apakah identitas saya terlindungi?", "Berapa lama proses investigasinya?"];
  return ["Bisa jelaskan lebih detail?", "Ada hal lain yang perlu saya tahu?"];
}

// ─── Action buttons after AI message ──────────────────────────────────────
function ActionButtons({ content, onOpen }: { content: string; onOpen: (m: ModalType, c: string) => void }) {
  const btns = detectActions(content);
  if (btns.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
      {btns.map((b) => (
        <button
          key={b.label}
          onClick={() => b.modal && onOpen(b.modal, content)}
          style={{
            padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 500,
            cursor: "pointer", border: `1px solid ${b.primary ? BLUE : "#d1d5db"}`,
            background: b.primary ? BLUE : "#fff",
            color: b.primary ? "#fff" : "#374151",
          }}
        >{b.label}</button>
      ))}
    </div>
  );
}

// ─── Quick reply chips ─────────────────────────────────────────────────────
function QuickReplies({ content, onSend }: { content: string; onSend: (t: string) => void }) {
  const chips = detectQuickReplies(content);
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
      {chips.map((c) => (
        <button
          key={c}
          onClick={() => onSend(c)}
          style={{
            padding: "6px 12px", borderRadius: 20, fontSize: 12,
            border: `1px solid ${BLUE}`, background: "#fff", color: BLUE,
            cursor: "pointer", whiteSpace: "nowrap",
          }}
        >{c}</button>
      ))}
    </div>
  );
}

// ─── Payslip parser ────────────────────────────────────────────────────────
const MONTH_ID_TO_EN: Record<string, string> = {
  januari: "January", februari: "February", maret: "March",
  april: "April", mei: "May", juni: "June", juli: "July",
  agustus: "August", september: "September", oktober: "October",
  november: "November", desember: "December",
};

interface ParsedPayslip {
  period: string;
  rows: Array<{ label: string; amount: string; isDeduction: boolean }>;
  netSalary: string | null;
  grossSalary: string | null;
  downloadUrl: string | null;
}

function parsePayslipFromContent(content: string, attachment?: MessageAttachment): ParsedPayslip {
  // Period detection
  let period = "March 2026";
  const periodMatch = content.match(
    /\b(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|january|february|march|may|june|july|august|october|november|december)\s+(\d{4})\b/i
  );
  if (periodMatch) {
    const raw = periodMatch[1].toLowerCase();
    const month = MONTH_ID_TO_EN[raw] ?? (periodMatch[1].charAt(0).toUpperCase() + periodMatch[1].slice(1));
    period = `${month} ${periodMatch[2]}`;
  } else if (attachment?.period?.label) {
    period = attachment.period.label;
  }

  // Net salary
  const netMatch = content.match(
    /(?:gaji\s*bersih|net\s*(?:pay|salary)|take[\s-]*home)[^0-9Rr]*(?:Rp\.?\s*)?([\d.,]+)/i
  );
  const netSalary = netMatch ? `Rp ${netMatch[1]}` : null;

  // Gross salary
  const grossMatch = content.match(
    /(?:gaji\s*kotor|gross\s*(?:pay|salary)|total\s*gaji|total\s*pendapatan)[^0-9Rr]*(?:Rp\.?\s*)?([\d.,]+)/i
  );
  const grossSalary = grossMatch ? `Rp ${grossMatch[1]}` : null;

  // Extract labeled line items: "Label ... Rp X" or "Label: Rp X"
  const lineRe = /^[-*•]?\s*([A-Za-z][A-Za-z\s()\/]+?)\s*[:\-–]\s*(?:Rp\.?\s*)?([\d.,]+)/gim;
  const rows: ParsedPayslip["rows"] = [];
  let m: RegExpExecArray | null;
  while ((m = lineRe.exec(content)) !== null) {
    const label = m[1].trim();
    const amount = `Rp ${m[2]}`;
    const lc = label.toLowerCase();
    const isDeduction = /pajak|pph|bpjs|potongan|deduct|pensiun|pension|iuran/.test(lc);
    // Skip duplicate net/gross from rows (shown separately)
    if (/gaji bersih|net pay|net salary|take.?home/.test(lc)) continue;
    rows.push({ label, amount, isDeduction });
  }

  // Download URL from attachment
  const downloadUrl =
    typeof attachment?.download_url === "string" && attachment.download_url
      ? attachment.download_url
      : null;

  return { period, rows, netSalary, grossSalary, downloadUrl };
}

// ─── Payslip Modal ─────────────────────────────────────────────────────────
function PayslipModal({
  session,
  lastAiContent,
  lastAiAttachment,
  onClose,
}: {
  session: Session | null;
  lastAiContent: string;
  lastAiAttachment?: MessageAttachment;
  onClose: () => void;
}) {
  const name = session ? getFirstName(session.email) : "Karyawan";
  const { period, rows, netSalary, grossSalary, downloadUrl } =
    parsePayslipFromContent(lastAiContent, lastAiAttachment);

  const earnings = rows.filter((r) => !r.isDeduction);
  const deductions = rows.filter((r) => r.isDeduction);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 520, maxHeight: "85vh", overflowY: "auto", background: "#fff", borderRadius: 16, padding: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111827" }}>Payslip – {period}</h2>
          {downloadUrl ? (
            <a
              href={downloadUrl}
              target="_blank"
              rel="noreferrer"
              style={{ background: BLUE, color: "#fff", border: "none", borderRadius: 8, padding: "7px 16px", fontSize: 13, fontWeight: 500, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, textDecoration: "none" }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
              Download PDF
            </a>
          ) : (
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", padding: 4 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20, padding: "14px 16px", background: "#f9fafb", borderRadius: 10 }}>
          <div>
            <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>Company</p>
            <p style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>PT Maju Bersama</p>
          </div>
          <div>
            <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>Employee</p>
            <p style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{name}</p>
          </div>
          <div>
            <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>Pay Period</p>
            <p style={{ fontSize: 13, fontWeight: 500, color: "#111827" }}>{period}</p>
          </div>
        </div>

        {earnings.length > 0 && (
          <Section title="Earnings">
            {earnings.map((r) => <Row key={r.label} label={r.label} value={r.amount} />)}
            {grossSalary && <Row label="Gross Salary" value={grossSalary} bold />}
          </Section>
        )}

        {deductions.length > 0 && (
          <Section title="Deductions">
            {deductions.map((r) => <Row key={r.label} label={r.label} value={`- ${r.amount}`} red />)}
          </Section>
        )}

        {earnings.length === 0 && deductions.length === 0 && (
          <div style={{ background: "#f9fafb", borderRadius: 10, padding: "14px 16px", marginBottom: 16, fontSize: 13, color: "#6b7280" }}>
            Rincian slip gaji tersedia di pesan di atas.
          </div>
        )}

        <div style={{ background: BLUE_LIGHT, borderRadius: 10, padding: "14px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>Net Salary</span>
          <span style={{ fontWeight: 700, fontSize: 18, color: BLUE }}>
            {netSalary ?? (grossSalary ? "—" : "Lihat pesan")}
          </span>
        </div>
      </div>
    </Overlay>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <p style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 8, borderBottom: "1px solid #e5e7eb", paddingBottom: 6 }}>{title}</p>
      {children}
    </div>
  );
}

function Row({ label, value, bold, red }: { label: string; value: string; bold?: boolean; red?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 13 }}>
      <span style={{ color: "#6b7280" }}>{label}</span>
      <span style={{ fontWeight: bold ? 700 : 500, color: red ? "#ef4444" : "#111827" }}>{value}</span>
    </div>
  );
}

// ─── Leave Modal ───────────────────────────────────────────────────────────
function LeaveModal({ session, onClose }: { session: Session | null; onClose: () => void }) {
  const name = session ? getFirstName(session.email) : "Karyawan";
  const cards = [
    { label: "Annual Leave", value: "12.5", unit: "days", color: "#10b981", bg: "#ecfdf5", note: "Next accrual: May 1, 2026" },
    { label: "Sick Leave", value: "8.0", unit: "days", color: "#ef4444", bg: "#fef2f2", note: "Next accrual: May 1, 2026" },
    { label: "Personal Leave", value: "3.0", unit: "days", color: "#8b5cf6", bg: "#f5f3ff", note: "Annual allocation" },
    { label: "Comp Time", value: "16", unit: "hours", color: "#0d9488", bg: "#f0fdfa", note: "Exp: July 31, 2026" },
  ];
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 560, background: "#fff", borderRadius: 16, padding: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111827" }}>Leave Details</h2>
            <p style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{name} • Employee ID: EMP-2587</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", padding: 4 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <p style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 12 }}>Current Leave Balance</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
          {cards.map((c) => (
            <div key={c.label} style={{ background: c.bg, borderRadius: 10, padding: "14px 16px" }}>
              <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>{c.label}</p>
              <p style={{ fontSize: 24, fontWeight: 700, color: c.color }}>
                {c.value} <span style={{ fontSize: 13, fontWeight: 500 }}>{c.unit}</span>
              </p>
              <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>{c.note}</p>
            </div>
          ))}
        </div>

        <div style={{ background: "#fffbeb", borderRadius: 8, padding: "10px 14px", marginBottom: 16, display: "flex", gap: 10, alignItems: "flex-start" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" style={{ flexShrink: 0, marginTop: 1 }}><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
          <p style={{ fontSize: 12, color: "#92400e" }}>
            <b>Annual Leave Policy:</b> You accrue 1.25 days of annual leave and 0.67 days of sick leave per month. Your next accrual will be processed on May 1, 2026.
          </p>
        </div>

        <p style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 8 }}>Recent Leave History</p>
        <div style={{ fontSize: 12, color: "#6b7280", borderBottom: "1px solid #f3f4f6", paddingBottom: 6, marginBottom: 16 }}>Annual Leave — Mar 20, 2026 (1 day) <span style={{ color: "#10b981", marginLeft: 8, fontWeight: 600 }}>Approved</span></div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
          <button onClick={onClose} style={{ flex: 1, padding: "9px", border: "1px solid #e5e7eb", borderRadius: 8, background: "#fff", color: "#374151", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>Close</button>
          <button style={{ flex: 1, padding: "9px", border: "none", borderRadius: 8, background: BLUE, color: "#fff", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>Request Leave</button>
        </div>
      </div>
    </Overlay>
  );
}

// ─── Confidential Report Modal ─────────────────────────────────────────────
function ReportModal({ onClose }: { onClose: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    await new Promise((r) => setTimeout(r, 1000));
    setSubmitted(true);
    setSubmitting(false);
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480, background: "#fff", borderRadius: 16, padding: 28 }}>
        {submitted ? (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div style={{ width: 56, height: 56, background: "#ecfdf5", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg>
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: "#111827", marginBottom: 8 }}>Report Submitted</h3>
            <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 20 }}>Your report has been received. Your identity is protected and only authorized HR personnel can access this.</p>
            <button onClick={onClose} style={{ padding: "9px 24px", background: BLUE, color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: "pointer" }}>Close</button>
          </div>
        ) : (
          <>
            <div style={{ textAlign: "center", marginBottom: 20 }}>
              <div style={{ width: 52, height: 52, background: "#fef2f2", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.8"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
              </div>
              <h2 style={{ fontSize: 17, fontWeight: 700, color: "#111827" }}>Confidential Report</h2>
              <p style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>Your identity will be protected</p>
            </div>

            <div style={{ background: "#eff6ff", borderRadius: 8, padding: "10px 14px", marginBottom: 20, display: "flex", gap: 10, alignItems: "flex-start" }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={BLUE} strokeWidth="2" style={{ flexShrink: 0, marginTop: 1 }}><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
              <p style={{ fontSize: 12, color: "#1e40af" }}>This report will only be accessible to authorized HR personnel. Your identity will be protected throughout the investigation process.</p>
            </div>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label="Type of Issue *">
                <select required style={fieldStyle}>
                  <option value="">Select issue type...</option>
                  <option>Workplace Harassment</option>
                  <option>Discrimination</option>
                  <option>Policy Violation</option>
                  <option>Safety Concern</option>
                  <option>Other</option>
                </select>
              </Field>

              <Field label="Date of Incident *">
                <input type="date" required style={fieldStyle} />
              </Field>

              <Field label="Location">
                <input type="text" placeholder="e.g. Office, Remote, Specific department" style={fieldStyle} />
              </Field>

              <Field label="Description of Incident *">
                <textarea
                  required
                  rows={4}
                  placeholder="Please provide as much detail as possible about what happened."
                  style={{ ...fieldStyle, resize: "none" as const }}
                />
              </Field>

              <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                <button type="button" onClick={onClose} style={{ flex: 1, padding: "9px", border: "1px solid #e5e7eb", borderRadius: 8, background: "#fff", color: "#374151", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>Cancel</button>
                <button type="submit" disabled={submitting} style={{ flex: 1, padding: "9px", border: "none", borderRadius: 8, background: submitting ? "#93c5fd" : BLUE, color: "#fff", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
                  {submitting ? "Submitting..." : "Submit Report"}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </Overlay>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#374151", marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );
}

const fieldStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px", border: "1px solid #d1d5db",
  borderRadius: 8, fontSize: 13, outline: "none",
  fontFamily: "inherit", color: "#111827", background: "#fff",
  boxSizing: "border-box",
};

// ─── Modal overlay ─────────────────────────────────────────────────────────
function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 100, padding: 20,
      }}
    >
      {children}
    </div>
  );
}

// ─── Message bubble ────────────────────────────────────────────────────────
function GeneratedDocumentCard({ attachment }: { attachment: MessageAttachment }) {
  const period =
    attachment.period && typeof attachment.period.label === "string"
      ? attachment.period.label
      : null;
  const fileName =
    typeof attachment.file_name === "string" && attachment.file_name
      ? attachment.file_name
      : "generated-document.pdf";
  const downloadUrl =
    typeof attachment.download_url === "string" && attachment.download_url
      ? attachment.download_url
      : null;
  const expiresAt =
    typeof attachment.download_url_expires_at === "string" &&
    attachment.download_url_expires_at
      ? new Date(attachment.download_url_expires_at).toLocaleString()
      : null;

  return (
    <div
      style={{
        marginTop: 10,
        background: "#f8fafc",
        border: "1px solid #dbeafe",
        borderRadius: 14,
        padding: "12px 14px",
        boxShadow: "0 1px 2px rgba(37,99,235,0.08)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#1d4ed8", marginBottom: 4 }}>
            Generated PDF
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", wordBreak: "break-word" }}>
            {fileName}
          </div>
          {period && (
            <div style={{ fontSize: 12, color: "#475569", marginTop: 2 }}>
              Period: {period}
            </div>
          )}
          {expiresAt && (
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
              Link expires: {expiresAt}
            </div>
          )}
          {!downloadUrl && (
            <div style={{ fontSize: 11, color: "#b45309", marginTop: 4 }}>
              Download URL is not available yet.
            </div>
          )}
        </div>
        {downloadUrl && (
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            style={{
              flexShrink: 0,
              padding: "8px 12px",
              borderRadius: 10,
              background: BLUE,
              color: "#fff",
              textDecoration: "none",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            Download
          </a>
        )}
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  userInitials,
  isLast,
  onQuickReply,
  onOpenModal,
}: {
  msg: Message;
  userInitials: string;
  isLast: boolean;
  onQuickReply: (t: string) => void;
  onOpenModal: (m: ModalType, content: string, attachment?: MessageAttachment) => void;
}) {
  const isUser = msg.role === "user";
  const isGuardrail = msg.metadata?.guardrail_triggered as boolean;
  const generatedDocuments = isUser ? [] : getGeneratedDocumentAttachments(msg);

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "flex-end", gap: 10 }}>
        <div style={{
          maxWidth: "65%", background: BLUE, color: "#fff",
          padding: "10px 15px", borderRadius: "18px 18px 4px 18px",
          fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap",
        }}>
          {msg.content}
        </div>
        <UserAvatar label={userInitials} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
      <BotAvatar />
      <div style={{ maxWidth: "72%" }}>
        <div style={{
          background: "#fff", border: "1px solid #e5e7eb",
          borderRadius: "18px 18px 18px 4px", padding: "12px 16px",
          fontSize: 14, lineHeight: 1.6, color: "#111827", whiteSpace: "pre-wrap",
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
        }}>
          {renderMessageContent(msg.content)}
          {isGuardrail && (
            <span style={{ display: "block", fontSize: 11, color: "#92400e", background: "#fef3c7", padding: "2px 8px", borderRadius: 4, marginTop: 6, width: "fit-content" }}>
              ⚠ Filtered by safety system
            </span>
          )}
        </div>
        {generatedDocuments.map((attachment, index) => (
          <GeneratedDocumentCard
            key={`${msg.id}-generated-document-${index}`}
            attachment={attachment}
          />
        ))}
        {isLast && !isGuardrail && (
          <ActionButtons
            content={msg.content}
            onOpen={(m, c) => onOpenModal(m, c, generatedDocuments[0])}
          />
        )}
        {isLast && !isGuardrail && <QuickReplies content={msg.content} onSend={onQuickReply} />}
      </div>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────
export default function ChatPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [activeConv, setActiveConv] = useState<Conversation | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState<ModalType>(null);
  const [modalContent, setModalContent] = useState<{ content: string; attachment?: MessageAttachment }>({ content: "" });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeConvRef = useRef<Conversation | null>(null);

  useEffect(() => { activeConvRef.current = activeConv; }, [activeConv]);

  useEffect(() => {
    api.get<Session>("/auth/me")
      .then(setSession)
      .catch(() => router.push("/chat/login"));
  }, [router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConv?.messages, loading]);

  async function ensureConversation(): Promise<Conversation> {
    // Use ref to always get latest value (avoids stale closure)
    if (activeConvRef.current) return activeConvRef.current;
    const conv = await api.post<Conversation>("/conversations", { title: "HR Chat" });
    setActiveConv(conv);
    activeConvRef.current = conv;
    return conv;
  }

  async function sendMessage(text?: string) {
    const msg = (text ?? message).trim();
    if (!msg || loading) return;
    setMessage("");
    setLoading(true);

    // Buat conversation dulu kalau belum ada
    let conv: Conversation;
    try {
      conv = await ensureConversation();
    } catch {
      setMessage(msg);
      setLoading(false);
      return;
    }

    // Optimistic: tambahkan pesan user langsung ke UI
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: conv.id,
      role: "user",
      content: msg,
      attachments: [],
      metadata: {},
      created_at: new Date().toISOString(),
    };
    setActiveConv((prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, tempUserMsg] }
        : { ...conv, messages: [tempUserMsg] }
    );

    try {
      const res = await api.post<ConversationExchangeResponse>(
        `/conversations/${conv.id}/messages`,
        { message: msg }
      );
      // Replace dengan response lengkap dari server
      setActiveConv(res.conversation);
    } catch {
      // Rollback optimistic message
      setActiveConv((prev) =>
        prev
          ? { ...prev, messages: prev.messages.filter((m) => m.id !== tempUserMsg.id) }
          : prev
      );
      setMessage(msg);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  const userInitials = session ? initials(getFirstName(session.email)) : "U";
  const displayName = session ? getFirstName(session.email) : "";
  // Sort messages by created_at to ensure correct render order
  const messages = [...(activeConv?.messages ?? [])].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
  const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf("assistant");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#f3f4f6", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>

      {/* ── Header ── */}
      <header style={{
        height: 56, background: "#fff", borderBottom: "1px solid #e5e7eb",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px", flexShrink: 0, zIndex: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8,
            background: `linear-gradient(135deg, ${BLUE}, ${BLUE_DARK})`,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <rect x="3" y="8" width="18" height="13" rx="3" stroke="white" strokeWidth="1.8" />
              <path d="M8 8V6a4 4 0 0 1 8 0v2" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="9" cy="14" r="1.2" fill="white" />
              <circle cx="15" cy="14" r="1.2" fill="white" />
            </svg>
          </div>
          <span style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>HR AI Assistant</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, color: "#374151", fontWeight: 500 }}>{displayName}</span>
          <div
            onClick={() => { clearToken(); router.push("/chat/login"); }}
            style={{
              width: 34, height: 34, borderRadius: "50%", background: BLUE,
              color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 700, cursor: "pointer",
            }}
          >{userInitials}</div>
        </div>
      </header>

      {/* ── Chat Area ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 20px" }}>

          {messages.length === 0 ? (
            /* ── Empty state ── */
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingTop: 80, gap: 0 }}>
              <div style={{
                width: 64, height: 64, borderRadius: "50%",
                background: `linear-gradient(135deg, ${BLUE}, ${BLUE_DARK})`,
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 20,
              }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="8" width="18" height="13" rx="3" stroke="white" strokeWidth="1.8" />
                  <path d="M8 8V6a4 4 0 0 1 8 0v2" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
                  <circle cx="9" cy="14" r="1.3" fill="white" />
                  <circle cx="15" cy="14" r="1.3" fill="white" />
                  <path d="M9 18h6" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <h1 style={{ fontSize: 24, fontWeight: 700, color: "#111827", marginBottom: 10 }}>HR AI Assistant</h1>
              <p style={{ fontSize: 14, color: "#6b7280", marginBottom: 32, textAlign: "center" }}>
                Ask anything about payroll, leave, reimbursement, or HR support
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, width: "100%", maxWidth: 500 }}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    style={{
                      padding: "11px 14px", border: `1px solid ${BLUE}`,
                      borderRadius: 10, background: "#fff", color: "#1e40af",
                      fontSize: 13, cursor: "pointer", textAlign: "left", lineHeight: 1.4,
                      transition: "background 0.15s",
                    }}
                  >{s}</button>
                ))}
              </div>
            </div>
          ) : (
            /* ── Messages ── */
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {messages.map((msg, i) => (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  userInitials={userInitials}
                  isLast={msg.role === "assistant" && i === lastAssistantIdx}
                  onQuickReply={sendMessage}
                  onOpenModal={(m, c, att) => { setModal(m); setModalContent({ content: c, attachment: att }); }}
                />
              ))}
              {loading && (
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <BotAvatar />
                  <div style={{
                    background: "#fff", border: "1px solid #e5e7eb",
                    borderRadius: "18px 18px 18px 4px", padding: "12px 16px",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                  }}>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      {[0, 1, 2].map((i) => (
                        <div key={i} style={{
                          width: 7, height: 7, borderRadius: "50%", background: "#d1d5db",
                          animation: `bounce 1.2s ${i * 0.2}s infinite`,
                        }} />
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* ── Input Bar ── */}
      <div style={{
        background: "#fff", borderTop: "1px solid #e5e7eb",
        padding: "14px 20px", flexShrink: 0,
      }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", gap: 10, alignItems: "center" }}>
          <input
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Type your question here..."
            style={{
              flex: 1, padding: "11px 16px", border: "1px solid #e5e7eb",
              borderRadius: 24, fontSize: 14, outline: "none", background: "#f9fafb",
              color: "#111827",
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !message.trim()}
            style={{
              width: 42, height: 42, borderRadius: "50%", border: "none",
              background: loading || !message.trim() ? "#d1d5db" : BLUE,
              color: "#fff", cursor: loading || !message.trim() ? "default" : "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "background 0.15s", flexShrink: 0,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Modals ── */}
      {modal === "payslip" && (
        <PayslipModal
          session={session}
          lastAiContent={modalContent.content}
          lastAiAttachment={modalContent.attachment}
          onClose={() => setModal(null)}
        />
      )}
      {modal === "leave" && <LeaveModal session={session} onClose={() => setModal(null)} />}
      {modal === "report" && <ReportModal onClose={() => setModal(null)} />}

      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
      `}</style>
    </div>
  );
}
