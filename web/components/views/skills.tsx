/**
 * Skills — marketplace and management.
 *
 * Grid of Skill cards with install/remove/enable/disable.
 * Category filters + search.
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import { Search, Download, Trash2, Shield, Globe, Star, CheckCircle } from "lucide-react";
import { useStore } from "@/lib/store";
import { api, ApiError, type SkillInfo, type MarketplaceSkill } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { SkeletonCard } from "@/components/ui/skeleton";
import { ApiErrorRecovery } from "@/components/ui/api-error-recovery";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

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
              aria-label={enabled ? `Disable ${skill.name}` : `Enable ${skill.name}`}
              className="gap-2"
            >
              {/* Animated toggle track */}
              <span
                className={cn(
                  "relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-300",
                  enabled ? "bg-[var(--success)]" : "bg-[var(--border-default)]",
                )}
              >
                <span
                  className={cn(
                    "inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-300",
                    enabled ? "translate-x-4" : "translate-x-0.5",
                  )}
                />
              </span>
              {enabled ? "On" : "Off"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRemove}
              className="text-[var(--error)]"
              aria-label={`Remove ${skill.name}`}
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
            aria-label={`Install ${skill.name}`}
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
// Marketplace Card (community browse)
// ═══════════════════════════════════════════════════════════════════════════

function MarketplaceCard({ skill, installedNames }: { skill: MarketplaceSkill; installedNames: Set<string> }) {
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(installedNames.has(skill.name));
  const toast = useToast();

  const icon = skill.icon || categoryIcons[skill.category] || "🧩";

  const handleInstall = async () => {
    setInstalling(true);
    try {
      await api.installFromMarketplace(skill.repo);
      setInstalled(true);
      toast.success(`${skill.name} installed!`);
    } catch {
      toast.error(`Failed to install ${skill.name}`);
    } finally {
      setInstalling(false);
    }
  };

  return (
    <Card variant="actionable" className="flex flex-col">
      <div className="text-center mb-3">
        <span className="text-3xl">{icon}</span>
        <h3 className="mt-2 font-semibold text-[15px] text-[var(--text-primary)]">
          {skill.name.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}
        </h3>
        <p className="text-xs text-[var(--text-tertiary)] mt-0.5 flex items-center justify-center gap-1">
          by @{skill.author}
          {skill.verified && (
            <CheckCircle className="h-3 w-3 text-[var(--brand-primary)]" />
          )}
        </p>
      </div>

      <p className="text-sm text-[var(--text-secondary)] text-center leading-relaxed flex-1">
        {skill.description}
      </p>

      {/* Stats */}
      <div className="flex justify-center gap-4 mt-3 text-xs text-[var(--text-tertiary)]">
        {skill.stars > 0 && (
          <span className="flex items-center gap-1">
            <Star className="h-3 w-3" /> {skill.stars}
          </span>
        )}
        {skill.downloads > 0 && (
          <span className="flex items-center gap-1">
            <Download className="h-3 w-3" /> {skill.downloads}
          </span>
        )}
      </div>

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

      {/* Install */}
      <div className="flex items-center justify-center mt-4 pt-3 border-t border-[var(--border-subtle)]">
        {installed ? (
          <Badge variant="brand">Installed</Badge>
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
// Browse Tab (marketplace)
// ═══════════════════════════════════════════════════════════════════════════

function BrowseTab({ installedNames }: { installedNames: Set<string> }) {
  const [marketplaceSkills, setMarketplaceSkills] = useState<MarketplaceSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | string | null>(null);
  const [search, setSearch] = useState("");

  const loadMarketplace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.browseMarketplace(search);
      setMarketplaceSkills(res.skills);
    } catch (err) {
      setError(err instanceof ApiError ? err : "Couldn't load marketplace.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadMarketplace();
  }, [loadMarketplace]);

  return (
    <div className="space-y-4">
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-tertiary)]" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search community skills..."
          className="pl-9"
          aria-label="Search marketplace"
        />
      </div>

      {error ? (
        <ApiErrorRecovery error={error} onRetry={loadMarketplace} />
      ) : loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : marketplaceSkills.length === 0 ? (
        <Card>
          <CardBody className="text-center py-12">
            <Globe className="h-8 w-8 mx-auto text-[var(--text-tertiary)] mb-3" />
            <p className="text-[var(--text-tertiary)]">
              {search ? "No community skills match your search." : "No community skills available yet."}
            </p>
            <p className="text-xs text-[var(--text-tertiary)] mt-1">
              Want to build one?{" "}
              <code className="text-[var(--brand-primary)]">omnibrain-skill init my-skill</code>
            </p>
          </CardBody>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {marketplaceSkills.map((skill, i) => (
            <div
              key={skill.name}
              className="animate-spring-in"
              style={{ animationDelay: `${i * 50}ms`, animationFillMode: "both" }}
            >
              <MarketplaceCard skill={skill} installedNames={installedNames} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main SkillsPage
// ═══════════════════════════════════════════════════════════════════════════

export function SkillsPage() {
  const { skills, setSkills } = useStore();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [tab, setTab] = useState<"installed" | "browse">("installed");

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getSkills();
      setSkills(res.skills);
    } catch (err) {
      setError(err instanceof ApiError ? err : "Couldn't load skills. The backend may be unreachable.");
    } finally {
      setLoading(false);
    }
  }, [setSkills]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const filtered = skills.filter((s) => {
    if (category !== "all" && s.category !== category) return false;
    if (search && !s.name.includes(search) && !s.description.includes(search))
      return false;
    return true;
  });

  const installedNames = new Set(skills.filter((s) => s.installed).map((s) => s.name));

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" role="region" aria-label="Skill store">
      <header>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Skill Store</h1>
        <p className="text-sm text-[var(--text-tertiary)] mt-1">
          Discover and install Skills to teach your AI new abilities.
        </p>
      </header>

      {/* ── Installed / Browse tabs ── */}
      <div className="flex gap-1 p-1 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] w-fit">
        <button
          onClick={() => setTab("installed")}
          className={cn(
            "px-4 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium transition-colors",
            tab === "installed"
              ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          Installed
        </button>
        <button
          onClick={() => setTab("browse")}
          className={cn(
            "px-4 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium transition-colors flex items-center gap-1.5",
            tab === "browse"
              ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          <Globe className="h-3.5 w-3.5" />
          Browse
        </button>
      </div>

      {tab === "browse" ? (
        <BrowseTab installedNames={installedNames} />
      ) : (
        <>
          {/* ── Filters ── */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-tertiary)]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills..."
                className="pl-9"
                aria-label="Search skills"
              />
            </div>
            <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="Skill categories">
              {categories.map((cat) => (
                <button
                  key={cat}
                  role="tab"
                  aria-selected={category === cat}
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
          {error ? (
            <ApiErrorRecovery error={error} onRetry={loadSkills} />
          ) : loading ? (
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
        </>
      )}
    </div>
  );
}
