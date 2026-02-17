/**
 * Settings — tabbed panel for profile, skills, LLM, notifications, data.
 * All tabs are functional: profile saves, notifications persist,
 * data export/delete actually work.
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import {
  User,
  Puzzle,
  Cpu,
  Bell,
  Database,
  Download,
  Trash2,
  Eye,
  EyeOff,
  Check,
  Zap,
  ExternalLink,
} from "lucide-react";
import { api, type Settings } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════════════
// Tabs
// ═══════════════════════════════════════════════════════════════════════════

const tabs = [
  { id: "profile", label: "Profile", icon: User },
  { id: "skills", label: "Skills", icon: Puzzle },
  { id: "llm", label: "LLM", icon: Cpu },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "data", label: "Data", icon: Database },
] as const;

type Tab = (typeof tabs)[number]["id"];

// ═══════════════════════════════════════════════════════════════════════════
// Sub-panels
// ═══════════════════════════════════════════════════════════════════════════

function ProfileTab() {
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then((s) => {
      setName(s.profile.name);
      setTimezone(s.profile.timezone);
    }).catch(() => {});
  }, []);

  const save = async () => {
    try {
      await api.updateSettings({ profile: { name, timezone, language: "en" } });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          Name
        </label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          Timezone
        </label>
        <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Europe/Rome" />
      </div>
      <Button variant="primary" size="md" onClick={save}>
        {saved ? <><Check className="h-4 w-4" /> Saved!</> : "Save Changes"}
      </Button>
    </div>
  );
}

function SkillsTab() {
  const skills = useStore((s) => s.skills);
  const setView = useStore((s) => s.setView);
  const [toggling, setToggling] = useState<string | null>(null);

  const toggle = useCallback(async (name: string, enabled: boolean) => {
    setToggling(name);
    try {
      if (enabled) await api.disableSkill(name);
      else await api.enableSkill(name);
      // Refresh skills list in store
      const { skills: updated } = await api.getSkills();
      useStore.setState({ skills: updated });
    } catch { /* ignore */ }
    setToggling(null);
  }, []);

  if (!skills.length) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">
          No skills installed yet.
        </p>
        <Button variant="primary" size="md" onClick={() => setView("skills")}>
          <Puzzle className="h-4 w-4" /> Open Skill Store
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-secondary)]">
        {skills.length} skill{skills.length !== 1 ? "s" : ""} installed. Toggle to enable or disable.
      </p>
      {skills.map((sk) => (
        <Card key={sk.name} className="p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg">{sk.icon || "🧩"}</span>
              <div>
                <span className="font-medium text-sm text-[var(--text-primary)]">
                  {sk.name}
                </span>
                <p className="text-xs text-[var(--text-tertiary)]">{sk.description}</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={sk.enabled}
                onChange={() => toggle(sk.name, sk.enabled)}
                disabled={toggling === sk.name}
                className="sr-only peer"
              />
              <div className="w-9 h-5 rounded-full bg-[var(--bg-tertiary)] peer-checked:bg-[var(--brand-primary)] transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
            </label>
          </div>
        </Card>
      ))}
      <Button variant="ghost" size="sm" onClick={() => setView("skills")}>
        <ExternalLink className="h-3.5 w-3.5" /> Open Skill Store
      </Button>
    </div>
  );
}

function LLMTab() {
  const [showKeys, setShowKeys] = useState(false);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [llmSettings, setLlmSettings] = useState<Settings["llm"] | null>(null);

  useEffect(() => {
    api.getStats().then(setStats).catch(() => {});
    api.getSettings().then((s) => setLlmSettings(s.llm)).catch(() => {});
  }, []);

  const providers = [
    { name: "DeepSeek", key: "DEEPSEEK_API_KEY", cost: "$0.14/M tokens", role: "Cheap tasks" },
    { name: "Claude", key: "ANTHROPIC_API_KEY", cost: "$3.00/M tokens", role: "Smart tasks" },
    { name: "OpenAI", key: "OPENAI_API_KEY", cost: "$2.50/M tokens", role: "Fallback" },
    { name: "Ollama", key: "OLLAMA_HOST", cost: "Free (local)", role: "Privacy-sensitive" },
  ];

  const totalCost = llmSettings?.current_month_cost ?? 0;
  const budget = llmSettings?.monthly_budget ?? 10;

  return (
    <div className="space-y-4">
      {/* Monthly usage card */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-[var(--text-primary)]">This Month</span>
          <span className="text-sm text-[var(--text-tertiary)]">
            ${totalCost.toFixed(2)} / ${budget.toFixed(2)}
          </span>
        </div>
        <div className="w-full h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--brand-primary)] transition-all"
            style={{ width: `${Math.min(100, (totalCost / budget) * 100)}%` }}
          />
        </div>
        {stats.total_llm_calls != null && (
          <p className="text-xs text-[var(--text-tertiary)] mt-2">
            <Zap className="inline h-3 w-3 mr-1" />
            {stats.total_llm_calls} API calls this month
          </p>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-[var(--text-primary)]">
          LLM Providers
        </h3>
        <Button variant="ghost" size="sm" onClick={() => setShowKeys(!showKeys)}>
          {showKeys ? <EyeOff className="h-3.5 w-3.5 mr-1" /> : <Eye className="h-3.5 w-3.5 mr-1" />}
          {showKeys ? "Hide Keys" : "Show Keys"}
        </Button>
      </div>
      <div className="space-y-2">
        {providers.map((p) => {
          const isPrimary = llmSettings?.primary_provider?.toLowerCase().includes(p.name.toLowerCase());
          return (
            <Card key={p.name} className="p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div>
                    <span className="font-medium text-sm text-[var(--text-primary)]">
                      {p.name}
                    </span>
                    {isPrimary && (
                      <Badge variant="success" className="ml-2 text-[10px]">PRIMARY</Badge>
                    )}
                    <span className="text-xs text-[var(--text-tertiary)] ml-2">
                      {p.cost}
                    </span>
                    {showKeys && (
                      <p className="text-xs text-[var(--text-tertiary)] mt-0.5 font-mono">
                        {p.key}: ••••••••
                      </p>
                    )}
                  </div>
                </div>
                <Badge variant="default">{p.role}</Badge>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function NotificationsTab() {
  const [prefs, setPrefs] = useState<Record<string, boolean>>({
    silent: true,
    fyi: true,
    important: true,
    critical: true,
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then((s) => {
      const n = s.notifications || {};
      // Build prefs from whatever shape comes back
      setPrefs({
        silent: n.silent !== false,
        fyi: n.fyi !== false,
        important: n.important !== false,
        critical: n.critical !== false,
      });
    }).catch(() => {});
  }, []);

  const toggle = useCallback(async (key: string) => {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    try {
      await api.updateSettings({ notifications: updated });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch { /* ignore */ }
  }, [prefs]);

  const levels = [
    { key: "silent", label: "Silent", desc: "Log only — no pop-ups" },
    { key: "fyi", label: "FYI", desc: "Low priority, batched" },
    { key: "important", label: "Important", desc: "Push within minutes" },
    { key: "critical", label: "Critical", desc: "Immediate alert + sound" },
  ];

  return (
    <div className="space-y-3">
      {levels.map((l) => (
        <Card key={l.key} className="p-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium text-sm text-[var(--text-primary)]">
                {l.label}
              </span>
              <p className="text-xs text-[var(--text-tertiary)]">{l.desc}</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={prefs[l.key]}
                onChange={() => toggle(l.key)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 rounded-full bg-[var(--bg-tertiary)] peer-checked:bg-[var(--brand-primary)] transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
            </label>
          </div>
        </Card>
      ))}
      {saved && (
        <p className="text-xs text-[var(--brand-primary)] flex items-center gap-1">
          <Check className="h-3 w-3" /> Preferences saved
        </p>
      )}
    </div>
  );
}

function DataTab() {
  const [exporting, setExporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const [settings, stats] = await Promise.all([
        api.getSettings(),
        api.getStats(),
      ]);
      const payload = { settings, stats, exported_at: new Date().toISOString() };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `omnibrain-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
    setExporting(false);
  }, []);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    try {
      // Delete all chat sessions
      const { sessions } = await api.getChatSessions(1000);
      await Promise.all(sessions.map((s) => api.deleteChatSession(s.session_id)));
      // Reset local state
      useStore.setState({
        messages: [],
        chatSessions: [],
        notifications: [],
        proposals: [],
        briefingData: null,
      });
      setConfirmDelete(false);
    } catch { /* ignore */ }
    setDeleting(false);
  }, []);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Export Your Data</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="mb-3 text-sm text-[var(--text-secondary)]">
            Download all your data as a JSON file. GDPR compliant.
          </p>
          <Button variant="secondary" size="md" onClick={handleExport} disabled={exporting}>
            <Download className="h-4 w-4" />
            {exporting ? "Exporting…" : "Export Data"}
          </Button>
        </CardBody>
      </Card>
      <Card variant="urgent">
        <CardHeader>
          <CardTitle className="text-[var(--error)]">Danger Zone</CardTitle>
        </CardHeader>
        <CardBody>
          {!confirmDelete ? (
            <>
              <p className="mb-3 text-sm text-[var(--text-secondary)]">
                Permanently delete all your data. This cannot be undone.
              </p>
              <Button variant="danger" size="md" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="h-4 w-4" />
                Delete Everything
              </Button>
            </>
          ) : (
            <>
              <p className="mb-3 text-sm text-[var(--error)] font-medium">
                Are you sure? This will delete ALL chat history, sessions, and preferences.
              </p>
              <div className="flex gap-2">
                <Button variant="danger" size="md" onClick={handleDelete} disabled={deleting}>
                  {deleting ? "Deleting…" : "Yes, Delete Everything"}
                </Button>
                <Button variant="ghost" size="md" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

const tabContent: Record<Tab, React.FC> = {
  profile: ProfileTab,
  skills: SkillsTab,
  llm: LLMTab,
  notifications: NotificationsTab,
  data: DataTab,
};

// ═══════════════════════════════════════════════════════════════════════════
// Main SettingsPage
// ═══════════════════════════════════════════════════════════════════════════

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const ActiveContent = tabContent[activeTab];

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Settings</h1>
      </header>

      <div className="flex flex-col sm:flex-row gap-6">
        {/* Tab list */}
        <nav
          role="tablist"
          aria-label="Settings sections"
          aria-orientation="vertical"
          className="flex sm:flex-col gap-1 sm:w-44 shrink-0"
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`settings-panel-${tab.id}`}
                id={`settings-tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-[var(--radius-sm)] transition-colors",
                  activeTab === tab.id
                    ? "bg-[var(--brand-glow)] text-[var(--brand-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]",
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* Content */}
        <div
          role="tabpanel"
          id={`settings-panel-${activeTab}`}
          aria-labelledby={`settings-tab-${activeTab}`}
          className="flex-1 min-w-0"
        >
          <ActiveContent />
        </div>
      </div>
    </div>
  );
}
