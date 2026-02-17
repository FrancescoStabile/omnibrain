import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chat",
  description: "Talk to your AI — it knows your emails, calendar, contacts, and patterns.",
};

export default function ChatRoute() {
  // Dynamic import avoids "use client" in the page module
  const { AppShell } = require("@/components/layout/app-shell");
  return <AppShell initialView="chat" />;
}
