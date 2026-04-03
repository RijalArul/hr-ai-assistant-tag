"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import type { LoginResponse } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<LoginResponse>("/auth/login", { email });
      setToken(res.access_token);
      const role = res.session.role;
      router.push(role === "hr_admin" || role === "it_admin" ? "/hr" : "/chat");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login gagal");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f8fafc" }}>
      <div style={{ width: 360, background: "#fff", borderRadius: 12, padding: 32, boxShadow: "0 1px 4px rgba(0,0,0,0.08)" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4, color: "#1e293b" }}>HR.ai</h1>
        <p style={{ color: "#64748b", marginBottom: 24, fontSize: 13 }}>Masuk dengan email karyawan</p>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 6, color: "#374151" }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="kamu@perusahaan.id"
              required
              style={{
                width: "100%", padding: "10px 12px", border: "1px solid #e2e8f0",
                borderRadius: 8, fontSize: 14, outline: "none",
              }}
            />
          </div>

          {error && (
            <p style={{ color: "#ef4444", fontSize: 13, background: "#fef2f2", padding: "8px 12px", borderRadius: 6 }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "11px", background: loading ? "#93c5fd" : "#1e40af",
              color: "#fff", border: "none", borderRadius: 8, fontSize: 14,
              fontWeight: 500, transition: "background 0.2s",
            }}
          >
            {loading ? "Masuk..." : "Masuk"}
          </button>
        </form>

        <div style={{ marginTop: 16, fontSize: 12, color: "#94a3b8", textAlign: "center", lineHeight: 1.8 }}>
          <p>Employee: fakhrul.rijal@majubersama.id</p>
          <p>HR Admin: siti.rahayu@majubersama.id</p>
        </div>
      </div>
    </div>
  );
}
