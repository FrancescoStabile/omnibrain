/**
 * Contacts — browse, search, and deeply understand your relationships.
 *
 * List view: cards with avatar, name, email, org, interaction count.
 * Detail view: rich profile with emails, meetings, topics, relationship score.
 */

"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Users,
  Search,
  Mail,
  Building,
  ArrowUpDown,
  ChevronRight,
  Loader2,
  Calendar,
  TrendingUp,
  Tag,
  MessageCircle,
  ArrowLeft,
  Clock,
} from "lucide-react";
import { api, type Contact, type ContactDetail } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { useNavigate } from "@/hooks/useNavigate";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

type SortKey = "name" | "interaction_count";

function contactInitials(c: Contact): string {
  if (c.name) {
    return c.name
      .split(" ")
      .map((w) => w[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
  }
  return c.email?.[0]?.toUpperCase() || "?";
}

const avatarColors = [
  "bg-blue-500/20 text-blue-400",
  "bg-green-500/20 text-green-400",
  "bg-amber-500/20 text-amber-400",
  "bg-purple-500/20 text-purple-400",
  "bg-pink-500/20 text-pink-400",
  "bg-cyan-500/20 text-cyan-400",
];

function avatarColor(email: string): string {
  let hash = 0;
  for (const c of email) hash = (hash * 31 + c.charCodeAt(0)) | 0;
  return avatarColors[Math.abs(hash) % avatarColors.length];
}

export function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("interaction_count");
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [contactDetail, setContactDetail] = useState<ContactDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getContacts(200);
        setContacts(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load contacts");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = useMemo(() => {
    let list = contacts;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.name?.toLowerCase().includes(q) ||
          c.email?.toLowerCase().includes(q) ||
          c.organization?.toLowerCase().includes(q),
      );
    }
    list = [...list].sort((a, b) => {
      if (sortKey === "interaction_count") return (b.interaction_count || 0) - (a.interaction_count || 0);
      return (a.name || "").localeCompare(b.name || "");
    });
    return list;
  }, [contacts, search, sortKey]);

  const openDetail = async (c: Contact) => {
    setSelectedContact(c);
    setContactDetail(null);
    setDetailLoading(true);
    try {
      const detail = await api.getContactDetail(c.email);
      setContactDetail(detail);
    } catch {
      setContactDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const navigate = useNavigate();
  const openChat = (context: string) => {
    useStore.setState({ messages: [] });
    navigate("chat");
    setTimeout(() => {
      useStore.getState().addMessage({
        role: "user",
        content: context,
        timestamp: new Date().toISOString(),
      });
    }, 200);
  };

  // ── Detail Panel ────────────────────────────────────────────────────────
  if (selectedContact) {
    const d = contactDetail;
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <button
          onClick={() => setSelectedContact(null)}
          className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to contacts
        </button>

        {/* Header */}
        <div className="flex items-center gap-4">
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-full text-xl font-bold shrink-0 ${avatarColor(selectedContact.email)}`}
          >
            {contactInitials(selectedContact)}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-[var(--text-primary)] truncate">
              {selectedContact.name || selectedContact.email}
            </h1>
            <p className="text-sm text-[var(--text-secondary)]">{selectedContact.email}</p>
            {selectedContact.organization && (
              <div className="flex items-center gap-1.5 mt-1 text-xs text-[var(--text-tertiary)]">
                <Building className="h-3 w-3" /> {selectedContact.organization}
              </div>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => openChat(`Tell me everything about ${selectedContact.name || selectedContact.email}. What should I know before our next interaction?`)}
          >
            <MessageCircle className="h-3.5 w-3.5" /> Ask
          </Button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-2xl font-bold text-[var(--text-primary)]">
                {d ? d.emails.count : (selectedContact.interaction_count || 0)}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">Emails</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-2xl font-bold text-[var(--text-primary)]">
                {d ? d.meetings.count : "—"}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">Meetings</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-sm font-medium text-[var(--text-primary)] capitalize">
                {selectedContact.relationship || "—"}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">Relationship</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {d?.contact.last_seen
                  ? new Date(d.contact.last_seen).toLocaleDateString()
                  : "—"}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">Last contact</p>
            </CardBody>
          </Card>
        </div>

        {/* Loading skeleton */}
        {detailLoading && (
          <div className="space-y-3">
            <div className="h-20 rounded-[var(--radius-lg)] bg-[var(--bg-secondary)] animate-pulse" />
            <div className="h-32 rounded-[var(--radius-lg)] bg-[var(--bg-secondary)] animate-pulse" />
          </div>
        )}

        {!detailLoading && d && (
          <>
            {/* Relationship score bar */}
            {d.relationship_score != null && d.relationship_score > 0 && (
              <Card>
                <CardBody className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <TrendingUp className="h-4 w-4 text-[var(--brand-primary)]" />
                      Relationship Strength
                    </div>
                    <span className="text-sm font-bold text-[var(--text-primary)]">
                      {Math.round(d.relationship_score * 100)}%
                    </span>
                  </div>
                  <div className="h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--brand-primary)] rounded-full transition-all duration-700"
                      style={{ width: `${Math.round(d.relationship_score * 100)}%` }}
                    />
                  </div>
                </CardBody>
              </Card>
            )}

            {/* Topics */}
            {d.topics && d.topics.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Tag className="h-4 w-4 text-[var(--accent-orange)]" />
                    <CardTitle>Discussion Topics</CardTitle>
                  </div>
                </CardHeader>
                <CardBody className="pt-0">
                  <div className="flex flex-wrap gap-2">
                    {d.topics.map((topic, i) => (
                      <button
                        key={i}
                        onClick={() => openChat(`What has ${selectedContact.name || selectedContact.email} said about "${topic}"?`)}
                        className="px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--brand-primary)]/30 transition-all"
                      >
                        {topic}
                      </button>
                    ))}
                  </div>
                </CardBody>
              </Card>
            )}

            {/* Recent emails */}
            {d.emails.recent && d.emails.recent.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-[var(--accent-blue)]" />
                    <CardTitle>Recent Emails</CardTitle>
                  </div>
                </CardHeader>
                <CardBody className="pt-0 space-y-3">
                  {d.emails.recent.slice(0, 5).map((email, i) => (
                    <div key={i} className="flex items-start gap-3 py-2 border-b border-[var(--border-subtle)] last:border-0">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                          {email.subject || "(no subject)"}
                        </p>
                        {email.snippet && (
                          <p className="text-xs text-[var(--text-secondary)] mt-0.5 line-clamp-2">
                            {email.snippet}
                          </p>
                        )}
                      </div>
                      {email.timestamp && (
                        <span className="text-xs text-[var(--text-tertiary)] shrink-0 mt-0.5">
                          {new Date(email.timestamp).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}

            {/* Recent meetings */}
            {d.meetings.recent && d.meetings.recent.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-[var(--brand-primary)]" />
                    <CardTitle>Recent Meetings</CardTitle>
                  </div>
                </CardHeader>
                <CardBody className="pt-0 space-y-3">
                  {d.meetings.recent.slice(0, 3).map((meeting, i) => (
                    <div key={i} className="flex items-start gap-3 py-2 border-b border-[var(--border-subtle)] last:border-0">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                          {meeting.title || "(untitled)"}
                        </p>
                        {meeting.attendee_count > 1 && (
                          <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
                            {meeting.attendee_count} attendees
                          </p>
                        )}
                      </div>
                      {meeting.timestamp && (
                        <span className="text-xs text-[var(--text-tertiary)] shrink-0 mt-0.5 flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {new Date(meeting.timestamp).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Contacts</h1>
        <span className="text-sm text-[var(--text-tertiary)]">{contacts.length} contacts</span>
      </div>

      {/* Search & Sort */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <Input
            placeholder="Search by name, email, or org…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <button
          onClick={() => setSortKey(sortKey === "interaction_count" ? "name" : "interaction_count")}
          className="flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ArrowUpDown className="h-3.5 w-3.5" />
          {sortKey === "interaction_count" ? "By activity" : "A–Z"}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-4 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--error)_8%,transparent)] text-sm text-[var(--error)]">
          {error}
          <button onClick={() => window.location.reload()} className="ml-2 underline">Retry</button>
        </div>
      )}

      {/* Contact Grid */}
      {!loading && !error && (
        <div className="grid gap-3 sm:grid-cols-2">
          {filtered.map((c) => (
            <Card
              key={c.email}
              className="cursor-pointer hover:border-[var(--brand-primary)]/30 transition-all"
              onClick={() => openDetail(c)}
            >
              <CardBody className="flex items-center gap-3 p-3">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold ${avatarColor(c.email)}`}
                >
                  {contactInitials(c)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
                    {c.name || c.email}
                  </p>
                  <p className="text-xs text-[var(--text-tertiary)] truncate">{c.email}</p>
                  {c.organization && (
                    <p className="text-xs text-[var(--text-tertiary)] truncate">{c.organization}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {c.interaction_count > 0 && (
                    <Badge className="text-[10px]">{c.interaction_count}</Badge>
                  )}
                  <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)]" />
                </div>
              </CardBody>
            </Card>
          ))}

          {filtered.length === 0 && (
            <div className="col-span-full py-12 text-center space-y-2">
              <Users className="mx-auto h-10 w-10 text-[var(--text-tertiary)] opacity-40" />
              <p className="text-sm font-medium text-[var(--text-secondary)]">
                {search ? "No contacts match your search" : "No contacts yet"}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">
                Contacts are extracted from your emails and conversations.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
