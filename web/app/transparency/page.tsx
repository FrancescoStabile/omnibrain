import type { Metadata } from "next";
import { ViewSync } from "@/components/layout/view-sync";

export const metadata: Metadata = {
  title: "Transparency",
  description: "See every LLM call your AI made — when, why, and what it cost. OmniBrain Layer 3.",
};

export default function TransparencyRoute() {
  return <ViewSync />;
}
