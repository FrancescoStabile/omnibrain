/**
 * Knowledge — natural language query interface to the knowledge graph.
 *
 * Users type questions like "What did Marco say about pricing?"
 * and get structured answers with source references.
 */

"use client";

import { useState, useCallback, type KeyboardEvent } from "react";
import { Brain, Search, ExternalLink, Clock, Loader2, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type KnowledgeReference } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

const exampleQueries = [
  "What do I know about pricing discussions?",
  "What did my recent emails discuss?",
  "Show patterns in my meetings",
  "Who contacted me most recently?",
];

export function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    summary: string;
    references: KnowledgeReference[];
    source_count?: number;
    error?: string;
  } | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  const search = useCallback(
    async (q?: string) => {
      const searchQuery = (q || query).trim();
      if (!searchQuery) return;

      setLoading(true);
      setResult(null);

      try {
        const res = await api.queryKnowledge(searchQuery);
        setResult(res);
        setHistory((prev) => {
          const next = [searchQuery, ...prev.filter((h) => h !== searchQuery)];
          return next.slice(0, 10);
        });
      } catch (e) {
        setResult({
          summary: "",
          references: [],
          error: e instanceof Error ? e.message : "Query failed",
        });
      } finally {
        setLoading(false);
      }
    },
    [query],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      search();
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Knowledge Graph</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask questions about everything OmniBrain has observed.
        </p>
      </div>

      {/* Search Bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Ask anything..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>
        <Button onClick={() => search()} disabled={loading || !query.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </div>

      {/* Suggestion chips (shown when no result) */}
      {!result && !loading && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {exampleQueries.map((eq) => (
              <Button
                key={eq}
                variant="ghost"
                size="sm"
                className="text-xs"
                onClick={() => {
                  setQuery(eq);
                  search(eq);
                }}
              >
                <Sparkles className="h-3 w-3 mr-1.5 text-amber-400" />
                {eq}
              </Button>
            ))}
          </div>

          {/* Recent queries */}
          {history.length > 0 && (
            <div>
              <p className="mb-2 text-sm text-muted-foreground">Recent:</p>
              <div className="flex flex-wrap gap-2">
                {history.map((h) => (
                  <Button
                    key={h}
                    variant="ghost"
                    size="sm"
                    className="text-xs"
                    onClick={() => {
                      setQuery(h);
                      search(h);
                    }}
                  >
                    <Clock className="h-3 w-3 mr-1.5" />
                    {h}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Empty illustration */}
          <div className="pt-8 text-center text-muted-foreground">
            <Brain className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p className="text-lg font-medium">Your knowledge base</p>
            <p className="mt-1 text-sm">
              OmniBrain builds a knowledge graph from your emails, calendar, and conversations.
              <br />
              Query it in natural language to find anything.
            </p>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-3 py-8">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Searching knowledge graph...</span>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4">
          {/* Error */}
          {result.error && (
            <Card className="border-destructive/50">
              <CardBody className="p-4">
                <p className="text-destructive text-sm">{result.error}</p>
              </CardBody>
            </Card>
          )}

          {/* Summary */}
          {result.summary && (
            <Card>
              <CardBody className="p-4">
                <div className="flex items-start gap-3">
                  <Brain className="mt-0.5 h-5 w-5 text-primary shrink-0" />
                  <div>
                    <div className="prose prose-sm dark:prose-invert max-w-none leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.summary}</ReactMarkdown>
                    </div>
                    {result.source_count != null && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Based on {result.source_count} sources
                      </p>
                    )}
                  </div>
                </div>
              </CardBody>
            </Card>
          )}

          {/* References */}
          {result.references.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold text-muted-foreground">References</h3>
              <div className="space-y-2">
                {result.references.map((ref, i) => (
                  <Card key={i} className="transition-colors hover:bg-accent/50">
                    <CardBody className="p-3">
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{ref.text}</ReactMarkdown>
                      </div>
                      <div className="mt-1.5 flex items-center gap-2">
                        <Badge className="bg-muted text-muted-foreground text-[10px]">{ref.source}</Badge>
                        {ref.date && <span className="text-xs text-muted-foreground">{ref.date}</span>}
                        {ref.score != null && (
                          <span className="text-xs text-muted-foreground">
                            relevance: {Math.round(ref.score * 100)}%
                          </span>
                        )}
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* No results */}
          {!result.error && !result.summary && result.references.length === 0 && (
            <div className="py-8 text-center text-muted-foreground">
              <p className="text-sm">No results found. Try rephrasing your query.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
