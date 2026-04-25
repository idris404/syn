import type { Metadata } from "next";
import Link from "next/link";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-sans",
  subsets: ["latin"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SYN Dashboard",
  description: "Clinical intelligence dashboard for SYN",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body
        className={`${spaceGrotesk.variable} ${ibmPlexMono.variable} antialiased`}
      >
        <div className="min-h-screen">
          <nav className="sticky top-0 z-40 border-b border-[var(--syn-border)] bg-[#0b0d13]/80 backdrop-blur">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
              <Link href="/" className="text-xl font-semibold tracking-tight text-[var(--syn-text)]">
                SYN Control Room
              </Link>
              <div className="flex gap-4 text-sm text-[var(--syn-muted)]">
                <Link href="/trials" className="transition hover:text-[var(--syn-text)]">Essais</Link>
                <Link href="/reports" className="transition hover:text-[var(--syn-text)]">Rapports</Link>
                <Link href="/ingest" className="transition hover:text-[var(--syn-text)]">Ingestion</Link>
              </div>
            </div>
          </nav>
          <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</div>
        </div>
      </body>
    </html>
  );
}
