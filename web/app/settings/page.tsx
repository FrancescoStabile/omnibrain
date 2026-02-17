import type { Metadata } from "next";
import { ViewSync } from "@/components/layout/view-sync";

export const metadata: Metadata = {
  title: "Settings",
  description: "Configure your OmniBrain — profile, LLM providers, notifications, and data management.",
};

export default function SettingsRoute() {
  return <ViewSync />;
}
