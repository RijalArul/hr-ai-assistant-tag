import Link from "next/link";

export default function Home() {
  return (
    <main style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#f8fafc", gap: 24 }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ fontSize: 36, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>HR.ai</h1>
        <p style={{ color: "#64748b", fontSize: 16 }}>Conversational HR Support Platform</p>
      </div>
      <div style={{ display: "flex", gap: 16 }}>
        <Link href="/chat/login" style={{ padding: "10px 24px", background: "#1e40af", color: "#fff", borderRadius: 8, fontWeight: 500 }}>
          Employee Chat
        </Link>
        <Link href="/hr" style={{ padding: "10px 24px", background: "#fff", color: "#1e40af", border: "1px solid #1e40af", borderRadius: 8, fontWeight: 500 }}>
          HR Dashboard
        </Link>
      </div>
    </main>
  );
}
