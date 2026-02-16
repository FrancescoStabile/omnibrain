/**
 * Settings — tabbed panel for profile, skills, LLM, notifications, data.
 */

"use client";

import { useState, useEffect } from "react";
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
} from "lucide-react";
import { api, type Settings } from "@/lib/api";
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

  useEffect(() => {
    api.getSettings().then((s) => {
      setName(s.profile.name);
      setTimezone(s.profile.timezone);
    }).catch(() => {});
  }, []);

  const save = () => {
    api.updateSettings({ profile: { name, timezone, language: "en" } }).catch(() => {});
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          Name
        </label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Francesco" />
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          Timezone
        </label>
        <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Europe/Rome" />
      </div>
      <Button variant="primary" size="md" onClick={save}>
        Save Changes
      </Button>
    </div>
  );
}

function SkillsTab() {
  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-secondary)]">
        Manage installed Skills. Enable, disable, or configure each one.
      </p>
      <Card>
        <CardBody className="text-center py-8 text-[var(--text-tertiary)]">
          Go to the Skill Store to manage your skills.
        </CardBody>
      </Card>
    </div>
  );
}

function LLMTab() {
  const [showKeys, setShowKeys] = useState(false);
  const [stats, setStats] = useState<Record<string, number>>({});

  useEffect(() => {
    api.getStats().then(setStats).catch(() => {});
  }, []);

  const providers = [
    { name: "DeepSeek", cost: "$0.14/M tokens", role: "Cheap tasks" },
    { name: "Claude", cost: "$3.00/M tokens", role: "Smart tasks" },
    { name: "OpenAI", cost: "$2.50/M tokens", role: "Fallback" },
    { name: "Ollama", cost: "Free (local)", role: "Privacy-sensitive" },
  ];

  return (
    <div className="space-y-4">
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
        {providers.map((p) => (
          <Card key={p.name} className="p-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium text-sm text-[var(--text-primary)]">
                  {p.name}
                </span>
                <span className="text-xs text-[var(--text-tertiary)] ml-2">
                  {p.cost}
                </span>
              </div>
              <Badge variant="default">{p.role}</Badge>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function NotificationsTab() {
  const levels = [
    { key: "silent", label: "Silent", desc: "Log only" },
    { key: "fyi", label: "FYI", desc: "Low priority, batched" },
    { key: "important", label: "Important", desc: "Push within minutes" },
    { key: "critical", label: "Critical", desc: "Immediate alert" },
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
              <input type="checkbox" defaultChecked className="sr-only peer" />
              <div className="w-9 h-5 rounded-full bg-[var(--bg-tertiary)] peer-checked:bg-[var(--brand-primary)] transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
            </label>
          </div>
        </Card>
      ))}
    </div>
  );
}

function DataTab() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Export Your Data</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="mb-3">
            Download all your data as a JSON file. GDPR compliant.
          </p>
          <Button variant="secondary" size="md">
            <Download className="h-4 w-4" />
            Export Data
          </Button>
        </CardBody>
      </Card>
      <Card variant="urgent">
        <CardHeader>
          <CardTitle className="text-[var(--error)]">Danger Zone</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="mb-3">
            Permanently delete all your data. This cannot be undone.
          </p>
          <Button variant="danger" size="md">
            <Trash2 className="h-4 w-4" />
            Delete Everything
          </Button>
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
