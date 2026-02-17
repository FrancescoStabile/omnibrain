import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Skill Store",
  description: "Discover and install Skills to teach your AI new abilities.",
};

export default function SkillsRoute() {
  const { AppShell } = require("@/components/layout/app-shell");
  return <AppShell initialView="skills" />;
}
