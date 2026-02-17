import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://omnibrain.dev";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "OmniBrain — Your AI That Remembers Everything",
    template: "%s | OmniBrain",
  },
  description:
    "Open-source AI platform that knows you, remembers everything, works 24/7, and grows smarter through community-built Skills. Local-first. MIT license.",
  keywords: [
    "AI assistant",
    "personal AI",
    "open source",
    "second brain",
    "proactive AI",
    "skill protocol",
    "local-first",
    "privacy",
  ],
  authors: [{ name: "Francesco Stabile" }],
  creator: "Francesco Stabile",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    apple: "/apple-touch-icon.png",
  },
  manifest: "/site.webmanifest",
  openGraph: {
    type: "website",
    siteName: "OmniBrain",
    title: "OmniBrain — Your AI That Remembers Everything",
    description:
      "Open-source AI platform that knows you, remembers everything, and works while you sleep. Connect Google, get insights in 30 seconds.",
    url: SITE_URL,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "OmniBrain — Your AI That Remembers Everything",
    description:
      "Open-source personal AI. Connects your email & calendar, builds a knowledge graph, works proactively. Free forever.",
    creator: "@Francesco_Sta",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
    { media: "(prefers-color-scheme: light)", color: "#7C3AED" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // AppShell is imported dynamically to avoid "use client" in the server layout.
  // It wraps the entire app — children (route pages) are rendered inside it
  // as lightweight ViewSync components that just set the active view.
  const AppShellWrapper = require("@/components/layout/app-shell-wrapper").AppShellWrapper;

  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('omnibrain-theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}})()`,
          }}
        />
      </head>
      <body className={`${GeistSans.variable} ${GeistMono.variable} font-sans antialiased`}>
        <AppShellWrapper>{children}</AppShellWrapper>
      </body>
    </html>
  );
}
