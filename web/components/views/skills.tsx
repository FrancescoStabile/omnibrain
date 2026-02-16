/**
 * Skills — marketplace and management.
 *
 * Grid of Skill cards with install/remove/enable/disable.
 * Category filters + search.
 */

"use client";

import { useEffect, useState } from "react";
import { Search, Download, Trash2, ToggleLeft, ToggleRight, Shield } from "lucide-react";
import { useStore } from "@/lib/store";
import { api, type SkillInfo } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { SkeletonCard } from "@/components/ui/skeleton";

// ═══════════════════════════════════════════════════════════════════════════
// Category icons (emoji for now)
// ═══════════════════════════════════════════════════════════════════════════

const categoryIcons: Record<string, string> = {
  communication: "📧",
  productivity: "📅",
  finance: "💰",
  entertainment: "🎵",
  developer: "💻",
  information: "📰",
  health: "🏋️",
  other: "🧩",
};

const categories = [
  "all",
  "communication",
  "productivity",
  "finance",
  "developer",
  "information",
  "other",
];

// ═══════════════════════════════════════════════════════════════════════════
// Skill Card
// ═══════════════════════════════════════════════════════════════════════════

function SkillCard({ skill }: { skill: SkillInfo }) {
  const [installing, setInstalling] = useState(false);
  const [enabled, setEnabled] = useState(skill.enabled);
  const setSkills = useStore((s) => s.setSkills);
  const skills = useStore((s) => s.skills);

  const icon = skill.icon || categoryIcons[skill.category] || "🧩";

  const handleInstall = async () => {
    setInstalling(true);
    try {
      await api.installSkill(skill.name);
      setSkills(
        skills.map((s) =>
          s.name === skill.name ? { ...s, installed: true, enabled: true } : s,
        ),
      );
    } finally {
      setInstalling(false);
    }
  };

  const handleRemove = async () => {
    try {
      await api.removeSkill(skill.name);
      setSkills(
        skills.map((s) =>
          s.name === skill.name ? { ...s, installed: false, enabled: false } : s,
        ),
      );
    } catch {
      // Ignore
    }
  };

  const handleToggle = async () => {
    const next = !enabled;
    try {
      if (next) {
        await api.enableSkill(skill.name);
      } else {
        await api.disableSkill(skill.name);
      }
      setEnabled(next);
    } catch {
      // Revert
    }
  };

  return (
    <Card variant="actionable" className="flex flex-col">
      {/* Icon + Name */}
      <div className="text-center mb-3">
        <span className="text-3xl">{icon}</span>
        <h3 className="mt-2 font-semibold text-[15px] text-[var(--text-primary)]">
          {skill.name
            .split("-")
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(" ")}
        </h3>
        <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
          by @{skill.author || "omnibrain"}
        </p>
      </div>

      {/* Description */}
      <p className="text-sm text-[var(--text-secondary)] text-center leading-relaxed flex-1">
        {skill.description}
      </p>

      {/* Permissions */}
      <div className="flex flex-wrap justify-center gap-1 mt-3">
        {skill.permissions.slice(0, 3).map((p) => (
          <Badge key={p} variant="default" className="text-[10px]">
            <Shield className="h-2.5 w-2.5 mr-0.5" />
            {p}
          </Badge>
        ))}
        {skill.permissions.length > 3 && (
          <Badge variant="default" className="text-[10px]">
            +{skill.permissions.length - 3}
          </Badge>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-center gap-2 mt-4 pt-3 border-t border-[var(--border-subtle)]">
        {skill.installed ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleToggle}
              title={enabled ? "Disable" : "Enable"}
            >
              {enabled ? (
                <ToggleRight className="h-4 w-4 text-[var(--success)]" />
              ) : (
                <ToggleLeft className="h-4 w-4" />
              )}
              {enabled ? "On" : "Off"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRemove}
              className="text-[var(--error)]"
              title="Remove"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={handleInstall}
            disabled={installing}
          >
            <Download className="h-3.5 w-3.5" />
            {installing ? "Installing..." : "Install"}
          </Button>
        )}
      </div>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main SkillsPage
// ═══════════════════════════════════════════════════════════════════════════

export function SkillsPage() {
  const { skills, setSkills } = useStore();
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await api.getSkills();
        if (!cancelled) setSkills(res.skills);
      } catch {
        // API not available — show empty
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [setSkills]);

  const filtered = skills.filter((s) => {
    if (category !== "all" && s.category !== category) return false;
    if (search && !s.name.includes(search) && !s.description.includes(search))
      return false;
    return true;
  });

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Skill Store</h1>
        <p className="text-sm text-[var(--text-tertiary)] mt-1">
          Discover and install Skills to teach your AI new abilities.
        </p>
      </header>

      {/* ── Filters ── */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-tertiary)]" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search skills..."
            className="pl-9"
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                category === cat
                  ? "bg-[var(--brand-primary)] text-white"
                  : "bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {cat === "all"
                ? "All"
                : `${categoryIcons[cat] || ""} ${cat.charAt(0).toUpperCase() + cat.slice(1)}`}
            </button>
          ))}
        </div>
      </div>

      {/* ── Grid ── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardBody className="text-center py-12">
            <p className="text-[var(--text-tertiary)]">
              {search
                ? "No skills match your search."
                : "No skills available yet. They're coming soon!"}
            </p>
          </CardBody>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((skill, i) => (
            <div
              key={skill.name}
              className="animate-spring-in"
              style={{ animationDelay: `${i * 50}ms`, animationFillMode: "both" }}
            >
              <SkillCard skill={skill} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
