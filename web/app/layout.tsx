import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "QuantumLabs — self-hosted AI agents",
  description:
    "Self-hosted tool-calling AI agents. Your model, your GPU. Safe edits, RAG memory, streaming API, human-in-the-loop approvals.",
};

// Root layout: yalniz html/body/font/dark. Sidebar kabuğu (app) grubuna tasindi;
// boylece landing (/) tam-genislik, app rotalari sidebar'li olur.
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-background text-foreground">{children}</body>
    </html>
  );
}
