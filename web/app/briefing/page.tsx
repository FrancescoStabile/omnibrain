import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Briefing",
  description: "Your daily intelligence report — emails, calendar, priorities, and proactive insights.",
};

export default function BriefingRoute() {
  const { AppShell } = require("@/components/layout/app-shell");
  return <AppShell initialView="briefing" />;
}
