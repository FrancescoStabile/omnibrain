/**
 * Chat — conversational AI interface.
 *
 * Messages stream in. Inline action buttons. Suggested prompts on empty state.
 */

"use client";

import { useRef, useState, useEffect, type FormEvent } from "react";
import { Send, Sparkles, Brain, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "@/lib/store";
import { streamChat, type ChatMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// ═══════════════════════════════════════════════════════════════════════════
// Suggested Prompts (empty state)
// ═══════════════════════════════════════════════════════════════════════════

const suggestions = [
  "What happened while I was asleep?",
  "What did Marco say about pricing?",
  "Summarize this week",
  "Show me unanswered emails",
];

// ═══════════════════════════════════════════════════════════════════════════
// Chat Bubble
// ═══════════════════════════════════════════════════════════════════════════

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

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

        {/* Actions */}
        {message.actions && message.actions.length > 0 && (
          <div className="flex gap-2 mt-3 pt-2 border-t border-white/10">
            {message.actions.map((action, i) => (
              <Button key={i} variant="ghost" size="sm" className="text-xs">
                {action.title}
              </Button>
            ))}
          </div>
        )}
      </div>

      {/* Copy button for AI messages */}
      {!isUser && (
        <button
          className="self-start ml-1 mt-2 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          onClick={() => navigator.clipboard.writeText(message.content)}
          title="Copy"
        >
          <Copy className="h-3.5 w-3.5" />
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
// Main ChatPage
// ═══════════════════════════════════════════════════════════════════════════

export function ChatPage() {
  const { messages, addMessage, appendToLastAssistant, chatLoading, setChatLoading } = useStore();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
    setChatLoading(true);

    // Add an empty assistant message to fill via streaming
    addMessage({
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    });

    try {
      for await (const event of streamChat(text.trim())) {
        if (event.type === "token" && event.content) {
          appendToLastAssistant(event.content);
        }
        if (event.type === "done") {
          break;
        }
      }
    } catch {
      // Replace the empty assistant message with an error
      appendToLastAssistant("Something went wrong. Please try again.");
    } finally {
      setChatLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
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
              <ChatBubble key={i} message={msg} />
            ))}
            {chatLoading && <TypingIndicator />}
          </div>
        )}
      </div>

      {/* ── Input ── */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 sm:px-6 py-3 sm:py-4">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto flex items-center gap-3"
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask me anything..."
            className={cn(
              "flex-1 h-11 px-4 rounded-[var(--radius-lg)]",
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
  );
}
