import type { Metadata } from "next";
import { ViewSync } from "@/components/layout/view-sync";

export const metadata: Metadata = {
  title: "Skill Store",
  description: "Discover and install Skills to teach your AI new abilities.",
};

export default function SkillsRoute() {
  return <ViewSync />;
}
