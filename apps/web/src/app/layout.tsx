import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HR.ai",
  description: "Conversational HR support platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
