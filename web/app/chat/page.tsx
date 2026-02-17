import type { Metadata } from "next";
import { ViewSync } from "@/components/layout/view-sync";

export const metadata: Metadata = {
  title: "Chat",
  description: "Talk to your AI — it knows your emails, calendar, contacts, and patterns.",
};

export default function ChatRoute() {
  return <ViewSync />;
}
