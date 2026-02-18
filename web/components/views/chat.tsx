/**
 * Chat — conversational AI interface.
 *
 * Messages stream in. Inline action buttons. Suggested prompts on empty state.
 */

"use client";

import { useRef, useState, useEffect, useMemo, useCallback, type FormEvent, type KeyboardEvent } from "react";
import { Send, Sparkles, Brain, Copy, Check, RotateCcw, AlertCircle, Plus, Trash2, MessageSquare, PanelLeftClose, PanelLeftOpen, Wrench, BookOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore, type View } from "@/lib/store";
import { streamChat, api, type ChatMessage, type ChatAction, type KnowledgeReference } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useNavigate } from "@/hooks/useNavigate";

// ═══════════════════════════════════════════════════════════════════════════
// Suggested Prompts (empty state) — contextual if onboarding result exists
// ═══════════════════════════════════════════════════════════════════════════

const DEFAULT_SUGGESTIONS = [
  "What happened while I was asleep?",
  "What did Marco say about pricing?",
  "Summarize this week",
  "Show me unanswered emails",
];

function buildSuggestions(onboardingResult: ReturnType<typeof useStore.getState>["onboardingResult"]): string[] {
  if (!onboardingResult) return DEFAULT_SUGGESTIONS;

  const suggestions: string[] = [];
  const stats = onboardingResult.stats || {};
  const insights = onboardingResult.insights || [];

  // Add personalised suggestions based on what was discovered
  if (stats.emails > 0) {
    suggestions.push("Show me my most important emails");
  }
  if (stats.events > 0) {
    suggestions.push("What's on my calendar this week?");
  }
  if (stats.contacts > 5) {
    suggestions.push("Who are my top contacts?");
  }

  // Use insight data for targeted suggestions
  for (const card of insights.slice(0, 2)) {
    if (card.icon === "mail" && card.title.includes("correspondent")) {
      const name = card.body.split(" sent")[0];
      if (name) suggestions.push(`What did ${name} write about?`);
    }
    if (card.icon === "calendar" && card.title.includes("meeting")) {
      suggestions.push("Brief me for my next meeting");
    }
  }

  // Ensure we always have 4 suggestions
  const remaining = DEFAULT_SUGGESTIONS.filter((s) => !suggestions.includes(s));
  while (suggestions.length < 4 && remaining.length) {
    suggestions.push(remaining.shift()!);
  }

  return suggestions.slice(0, 4);
}

// ═══════════════════════════════════════════════════════════════════════════
// Source Citations
// ═══════════════════════════════════════════════════════════════════════════

function SourceCitations({ refs }: { refs: KnowledgeReference[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? refs : refs.slice(0, 2);

  return (
    <div className="mt-3 pt-2 border-t border-[var(--border-subtle)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[10px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors mb-1.5"
      >
        <BookOpen className="h-3 w-3" />
        {refs.length} source{refs.length !== 1 ? "s" : ""}
        {refs.length > 2 && (
          <span className="ml-1 text-[var(--brand-primary)]">{expanded ? "▲ less" : "▼ more"}</span>
        )}
      </button>
      <div className="space-y-1">
        {visible.map((ref, i) => (
          <div
            key={i}
            className="flex items-start gap-2 px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--bg-tertiary)]"
          >
            <span className="shrink-0 mt-0.5 h-3.5 w-3.5 rounded-full bg-[var(--brand-primary)]/20 text-[var(--brand-primary)] text-[9px] flex items-center justify-center font-semibold">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-[11px] text-[var(--text-secondary)] leading-snug line-clamp-2">{ref.text}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-[var(--text-tertiary)]">{ref.source}</span>
                {ref.date && <span className="text-[10px] text-[var(--text-tertiary)]">· {ref.date}</span>}
                {ref.score !== undefined && (
                  <span className="text-[10px] text-[var(--text-tertiary)]">· {Math.round(ref.score * 100)}%</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Follow-up Suggestions
// ═══════════════════════════════════════════════════════════════════════════

function FollowUpSuggestions({ followups, onSend }: { followups: string[]; onSend: (action: ChatAction) => void }) {
  return (
    <div className="mt-3 pt-2 border-t border-[var(--border-subtle)] space-y-1.5">
      <span className="text-[10px] text-[var(--text-tertiary)]">Follow up:</span>
      <div className="flex flex-wrap gap-1.5">
        {followups.map((f, i) => (
          <button
            key={i}
            onClick={() => onSend({ type: "draft", title: f, data: { prompt: f } })}
            className="px-2.5 py-1 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--brand-primary)]/30 transition-colors"
          >
            {f}
          </button>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Chat Bubble
// ═══════════════════════════════════════════════════════════════════════════

function ChatBubble({ message, onAction }: { message: ChatMessage; onAction: (action: ChatAction) => void }) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const timestamp = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-end" : "justify-start",
        "animate-[fade-in_200ms_ease-out]",
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-[var(--radius-lg)] px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-[var(--brand-primary)] text-white"
            : "bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-subtle)]",
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:my-2 prose-pre:my-2 prose-code:text-[var(--brand-primary)] prose-code:bg-[var(--bg-tertiary)] prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-a:text-[var(--brand-primary)] prose-strong:text-[var(--text-primary)]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Source citations */}
        {!isUser && message.references && message.references.length > 0 && (
          <SourceCitations refs={message.references} />
        )}

        {/* Suggested follow-ups */}
        {!isUser && message.suggested_followups && message.suggested_followups.length > 0 && (
          <FollowUpSuggestions followups={message.suggested_followups} onSend={onAction} />
        )}

        {/* Actions */}
        {message.actions && message.actions.length > 0 && (
          <div className="flex gap-2 mt-3 pt-2 border-t border-white/10">
            {message.actions.map((action, i) => (
              <Button key={i} variant="ghost" size="sm" className="text-xs" onClick={() => onAction(action)}>
                {action.title}
              </Button>
            ))}
          </div>
        )}

        {/* Timestamp */}
        {timestamp && (
          <span className="block mt-1.5 text-[10px] opacity-50">
            {timestamp}
          </span>
        )}
      </div>

      {/* Copy button for AI messages */}
      {!isUser && (
        <button
          className="self-start ml-1 mt-2 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy"}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-[var(--success)]" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Typing Indicator
// ═══════════════════════════════════════════════════════════════════════════

function TypingIndicator() {
  return (
    <div className="flex justify-start" role="status" aria-label="Assistant is typing">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] px-4 py-3 flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 bg-[var(--text-tertiary)] rounded-full animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Tool Call Indicator — shows agent tool execution inline
// ═══════════════════════════════════════════════════════════════════════════

function ToolCallIndicator({ toolName, done }: { toolName: string; done?: boolean }) {
  // Format tool names nicely: "search_emails" → "Searching emails"
  const label = toolName
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="flex justify-start animate-[fade-in_200ms_ease-out]">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-xs text-[var(--text-tertiary)]">
        <Wrench className={cn("h-3 w-3 shrink-0", !done && "animate-[spin_2s_linear_infinite]")} />
        <span>{done ? `✓ ${label}` : label}</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main ChatPage
// ═══════════════════════════════════════════════════════════════════════════

export function ChatPage() {
  // Individual selectors prevent re-renders from unrelated store changes
  const messages = useStore((s) => s.messages);
  const addMessage = useStore((s) => s.addMessage);
  const appendToLastAssistant = useStore((s) => s.appendToLastAssistant);
  const setMessages = useStore((s) => s.setMessages);
  const chatLoading = useStore((s) => s.chatLoading);
  const setChatLoading = useStore((s) => s.setChatLoading);
  const chatSessionId = useStore((s) => s.chatSessionId);
  const setChatSessionId = useStore((s) => s.setChatSessionId);
  const chatSessions = useStore((s) => s.chatSessions);
  const setChatSessions = useStore((s) => s.setChatSessions);
  const onboardingResult = useStore((s) => s.onboardingResult);
  const [input, setInput] = useState("");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [activeTools, setActiveTools] = useState<{ name: string; done: boolean }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const suggestions = useMemo(() => buildSuggestions(onboardingResult), [onboardingResult]);

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, []);

  // Load sessions list
  useEffect(() => {
    api.getChatSessions(50).then((d) => setChatSessions(d.sessions)).catch(() => {});
  }, [setChatSessions]);

  // Load chat history from backend on mount (session persistence)
  useEffect(() => {
    if (historyLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        const { api } = await import("@/lib/api");
        const data = await api.getChatHistory(chatSessionId);
        if (!cancelled && data.messages?.length) {
          const loaded: ChatMessage[] = data.messages.map((m: { role: string; content: string; timestamp?: string }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: m.timestamp || "",
          }));
          setMessages(loaded);
        }
      } catch {
        // Backend might not be ready yet, that's fine
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, [chatSessionId, historyLoaded, setMessages]);

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, chatLoading]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const send = async (text: string) => {
    if (!text.trim() || chatLoading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text.trim(),
      timestamp: new Date().toISOString(),
    };
    addMessage(userMsg);
    setInput("");
    setFailedMessage(null);
    setChatLoading(true);
    // Reset textarea height
    if (inputRef.current) inputRef.current.style.height = "auto";

    // Add an empty assistant message to fill via streaming
    addMessage({
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    });

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);

      for await (const event of streamChat(text.trim(), chatSessionId)) {
        if (event.type === "token" && event.content) {
          appendToLastAssistant(event.content);
        } else if (event.type === "tool_start" && (event as { tool_name?: string }).tool_name) {
          const toolName = (event as { tool_name: string }).tool_name;
          setActiveTools((prev) => [...prev, { name: toolName, done: false }]);
        } else if (event.type === "tool_result" && (event as { tool_name?: string }).tool_name) {
          const toolName = (event as { tool_name: string }).tool_name;
          setActiveTools((prev) =>
            prev.map((t) => t.name === toolName ? { ...t, done: true } : t)
          );
          // Remove completed tool after a short delay
          setTimeout(() => {
            setActiveTools((prev) => prev.filter((t) => !(t.name === toolName && t.done)));
          }, 1200);
        } else if (event.type === "done") {
          // Backend may return session_id — store it
          if (event.session_id && event.session_id !== chatSessionId) {
            setChatSessionId(event.session_id);
          }
          // Attach references and follow-up suggestions to the last assistant message
          const doneEvent = event as {
            session_id?: string;
            references?: import("@/lib/api").KnowledgeReference[];
            suggested_followups?: string[];
          };
          if (doneEvent.references?.length || doneEvent.suggested_followups?.length) {
            setMessages(
              useStore.getState().messages.map((m, i, arr) =>
                i === arr.length - 1 && m.role === "assistant"
                  ? {
                      ...m,
                      references: doneEvent.references,
                      suggested_followups: doneEvent.suggested_followups,
                    }
                  : m
              )
            );
          }
          break;
        }
      }
      clearTimeout(timeout);
    } catch {
      // Replace partial content with error message
      setFailedMessage(text.trim());
      setMessages(
        useStore.getState().messages.map((m, i, arr) =>
          i === arr.length - 1 && m.role === "assistant"
            ? { ...m, content: "⚠️ Something went wrong. Please try again." }
            : m
        )
      );
    } finally {
      setChatLoading(false);
      setActiveTools([]);  // Clear any pending tool indicators
    }
  };

  const handleRetry = () => {
    if (failedMessage) {
      // Remove the error message
      setMessages(useStore.getState().messages.slice(0, -2));
      send(failedMessage);
    }
  };

  const startNewChat = () => {
    const newId = `session-${Date.now()}`;
    setChatSessionId(newId);
    setMessages([]);
    setHistoryLoaded(true);
    setFailedMessage(null);
    inputRef.current?.focus();
    // Refresh sessions list
    api.getChatSessions(50).then((d) => setChatSessions(d.sessions)).catch(() => {});
  };

  const switchSession = async (sessionId: string) => {
    if (sessionId === chatSessionId) return;
    setTransitioning(true);
    // Brief fade-out before switching
    await new Promise((r) => setTimeout(r, 150));
    setChatSessionId(sessionId);
    setHistoryLoaded(false);
    setMessages([]);
    setFailedMessage(null);
    setSessionsOpen(false);
    // Fade back in
    requestAnimationFrame(() => setTransitioning(false));
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await api.deleteChatSession(sessionId);
      setChatSessions(chatSessions.filter((s) => s.session_id !== sessionId));
      if (sessionId === chatSessionId) startNewChat();
    } catch {
      // Ignore delete errors
    }
  };

  const handleAction = useCallback(
    (action: ChatAction) => {
      switch (action.type) {
        case "navigate":
          if (action.data?.view) {
            navigate(action.data.view as View);
          }
          break;
        case "approve":
          if (action.data?.id) {
            api.approveProposal(Number(action.data.id));
          }
          break;
        case "draft":
          if (action.data?.prompt) {
            send(String(action.data.prompt));
          }
          break;
        case "link":
          if (action.data?.url) {
            window.open(String(action.data.url), "_blank", "noopener");
          }
          break;
        default:
          break;
      }
    },
    [navigate, chatSessionId],
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full h-[100dvh] sm:h-full">
      {/* ── Header with session controls ── */}
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-2">
        <Button
          variant="icon"
          size="sm"
          onClick={() => setSessionsOpen(!sessionsOpen)}
          title="Chat sessions"
        >
          {sessionsOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </Button>
        <span className="text-sm font-medium text-[var(--text-secondary)] truncate flex-1">
          {chatSessionId === "default" ? "Chat" : chatSessionId.replace("session-", "Chat #")}
        </span>
        <Button variant="ghost" size="sm" onClick={startNewChat} title="New chat">
          <Plus className="h-4 w-4 mr-1" /> New
        </Button>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* ── Session Sidebar ── */}
        {sessionsOpen && (
          <div className="w-56 shrink-0 border-r border-[var(--border-subtle)] overflow-y-auto bg-[var(--bg-secondary)]">
            <div className="p-2 space-y-1">
              {chatSessions.length === 0 && (
                <p className="px-2 py-4 text-xs text-muted-foreground text-center">No sessions yet</p>
              )}
              {chatSessions.map((s) => (
                <div
                  key={s.session_id}
                  className={cn(
                    "group flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs cursor-pointer transition-colors",
                    s.session_id === chatSessionId
                      ? "bg-[var(--brand-glow)] text-[var(--brand-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]",
                  )}
                  onClick={() => switchSession(s.session_id)}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate">
                      {s.session_id === "default" ? "Main Chat" : s.session_id.replace("session-", "#")}
                    </p>
                    <p className="text-[10px] text-muted-foreground">{s.message_count} msgs</p>
                  </div>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteSession(s.session_id);
                    }}
                    title="Delete session"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Main chat area ── */}
        <div className={cn(
          "flex flex-col flex-1 min-w-0 transition-opacity duration-150",
          transitioning ? "opacity-0" : "opacity-100",
        )}>
      {/* ── Messages ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-8">
            <div className="text-center space-y-3">
              <div className="h-16 w-16 mx-auto rounded-full bg-[var(--brand-glow)] flex items-center justify-center">
                <Brain className="h-8 w-8 text-[var(--brand-primary)]" />
              </div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                Ask me anything
              </h2>
              <p className="text-sm text-[var(--text-tertiary)] max-w-sm">
                I know your emails, calendar, contacts, and patterns. Try one of
                these:
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 max-w-lg">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="px-4 py-2 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <Sparkles className="inline h-3.5 w-3.5 mr-1.5 text-[var(--brand-primary)]" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div role="log" aria-live="polite" aria-label="Chat messages" className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg, i) => (
              <ChatBubble key={i} message={msg} onAction={handleAction} />
            ))}
            {failedMessage && !chatLoading && (
              <div className="flex justify-start">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-[var(--accent-red)] gap-1"
                  onClick={handleRetry}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Retry
                </Button>
              </div>
            )}
            {activeTools.map((t, i) => (
              <ToolCallIndicator key={`${t.name}-${i}`} toolName={t.name} done={t.done} />
            ))}
            {chatLoading && activeTools.length === 0 && <TypingIndicator />}
          </div>
        )}
      </div>

      {/* ── Input ── */}
      <div className="sticky bottom-0 border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 sm:px-6 py-3 sm:py-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto flex items-center gap-3"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              resizeTextarea();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask me anything..."
            rows={1}
            className={cn(
              "flex-1 min-h-[44px] max-h-[200px] px-4 py-2.5 rounded-[var(--radius-lg)] resize-none",
              "bg-[var(--bg-secondary)] border border-[var(--border-default)]",
              "text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]",
              "focus:border-[var(--brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--brand-primary)]",
              "transition-colors duration-150",
            )}
            disabled={chatLoading}
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            disabled={!input.trim() || chatLoading}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
        </div>
      </div>
    </div>
  );
}
