import type { Metadata } from "next";
import { ViewSync } from "@/components/layout/view-sync";

export const metadata: Metadata = {
  title: "Briefing",
  description: "Your daily intelligence report — emails, calendar, priorities, and proactive insights.",
};

export default function BriefingRoute() {
  return <ViewSync />;
}
