/**
 * Contacts — browse extracted contacts with importance scoring.
 *
 * Grid of cards showing name, email, relationship, interaction count.
 * Search/filter by name. Click for detail view.
 */

"use client";

import { useEffect, useState, useMemo } from "react";
import { Users, Search, Mail, Building, ArrowUpDown, ChevronRight, Loader2 } from "lucide-react";
import { api, type Contact } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";

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
  const [contactDetail, setContactDetail] = useState<Record<string, unknown> | null>(null);
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
      const detail = await api.getKnowledgeContact(c.email);
      setContactDetail(detail);
    } catch {
      setContactDetail({ error: "Could not load detail" });
    } finally {
      setDetailLoading(false);
    }
  };

  // Detail panel
  if (selectedContact) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
        <Button variant="ghost" size="sm" onClick={() => setSelectedContact(null)}>
          ← Back to contacts
        </Button>

        <div className="flex items-center gap-4">
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-full text-lg font-bold ${avatarColor(selectedContact.email)}`}
          >
            {contactInitials(selectedContact)}
          </div>
          <div>
            <h1 className="text-2xl font-bold">{selectedContact.name || selectedContact.email}</h1>
            <p className="text-sm text-muted-foreground">{selectedContact.email}</p>
            {selectedContact.organization && (
              <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Building className="h-3 w-3" />
                {selectedContact.organization}
              </div>
            )}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-2xl font-bold">{selectedContact.interaction_count || 0}</p>
              <p className="text-xs text-muted-foreground">Interactions</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-sm font-medium">{selectedContact.relationship || "Unknown"}</p>
              <p className="text-xs text-muted-foreground">Relationship</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4 text-center">
              <p className="text-sm font-medium truncate">{selectedContact.organization || "—"}</p>
              <p className="text-xs text-muted-foreground">Organization</p>
            </CardBody>
          </Card>
        </div>

        {/* Knowledge graph detail */}
        <Card>
          <CardBody className="p-4">
            <h3 className="mb-3 font-semibold">Knowledge Graph</h3>
            {detailLoading && <Loader2 className="h-5 w-5 animate-spin" />}
            {!detailLoading && contactDetail && "error" in contactDetail && (
              <p className="text-sm text-muted-foreground">{String(contactDetail.error)}</p>
            )}
            {!detailLoading && contactDetail && !("error" in contactDetail) && (
              <pre className="max-h-64 overflow-auto rounded bg-muted/50 p-3 text-xs">
                {JSON.stringify(contactDetail, null, 2)}
              </pre>
            )}
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Contacts</h1>
        <span className="text-sm text-muted-foreground">{contacts.length} contacts</span>
      </div>

      {/* Search & Sort */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name, email, or org..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSortKey(sortKey === "interaction_count" ? "name" : "interaction_count")}
          title={`Sort by ${sortKey === "interaction_count" ? "name" : "interactions"}`}
        >
          <ArrowUpDown className="h-4 w-4 mr-1" />
          {sortKey === "interaction_count" ? "By activity" : "A–Z"}
        </Button>
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
        <Card className="border-destructive/50">
          <CardBody>
            <p className="text-destructive">{error}</p>
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => window.location.reload()}>
              Try Again
            </Button>
          </CardBody>
        </Card>
      )}

      {/* Contact Grid */}
      {!loading && !error && (
        <div className="grid gap-3 sm:grid-cols-2">
          {filtered.map((c) => (
            <Card
              key={c.email}
              className="cursor-pointer transition-colors hover:bg-accent/50"
              onClick={() => openDetail(c)}
            >
              <CardBody className="flex items-center gap-3 p-3">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold ${avatarColor(c.email)}`}
                >
                  {contactInitials(c)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{c.name || c.email}</p>
                  <p className="text-xs text-muted-foreground truncate">{c.email}</p>
                  {c.organization && (
                    <p className="text-xs text-muted-foreground truncate">{c.organization}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {c.interaction_count > 0 && (
                    <Badge className="bg-muted text-muted-foreground text-[10px]">
                      {c.interaction_count} msgs
                    </Badge>
                  )}
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardBody>
            </Card>
          ))}

          {filtered.length === 0 && (
            <div className="col-span-full py-12 text-center text-muted-foreground">
              <Users className="mx-auto mb-3 h-10 w-10 opacity-50" />
              <p className="text-lg font-medium">
                {search ? "No contacts match your search" : "No contacts yet"}
              </p>
              <p className="text-sm">Contacts are extracted from your emails and conversations.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
