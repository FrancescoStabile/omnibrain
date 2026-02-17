import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Settings",
  description: "Configure your OmniBrain — profile, LLM providers, notifications, and data management.",
};

export default function SettingsRoute() {
  const { AppShell } = require("@/components/layout/app-shell");
  return <AppShell initialView="settings" />;
}
