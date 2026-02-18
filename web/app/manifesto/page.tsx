import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Manifesto — Your AI Must Be Yours",
  description:
    "The founding document of OmniBrain. Why personal AI must be open, local, and yours.",
  openGraph: {
    title: "OmniBrain Manifesto — Your AI Must Be Yours",
    description:
      "The most powerful technology ever created is being built behind closed doors. OmniBrain is the open alternative.",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "OmniBrain Manifesto",
    description: "Your AI must be yours. Read the founding document.",
  },
};

export default function ManifestoPage() {
  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* ── Header ────────────────────────────────────── */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[var(--bg-primary)]/80 border-b border-[var(--border-primary)]">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 group">
            <div className="h-8 w-8 rounded-lg bg-[var(--brand-primary)] flex items-center justify-center">
              <span className="text-white font-bold text-sm">O</span>
            </div>
            <span className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)] transition-colors">
              OmniBrain
            </span>
          </a>
          <div className="flex items-center gap-3">
            <ShareButtons />
            <a
              href="https://github.com/OmniBrain-Team/omnibrain"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--brand-primary)] text-white text-sm font-medium hover:bg-[var(--brand-hover)] transition-colors"
            >
              Install
            </a>
          </div>
        </div>
      </header>

      {/* ── Hero ──────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pt-20 pb-16 text-center">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-[var(--brand-primary)] mb-6">
          A Founding Document
        </p>
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold text-[var(--text-primary)] leading-[1.1] tracking-tight mb-6">
          Your AI Must Be Yours.
        </h1>
        <p className="text-lg text-[var(--text-secondary)] max-w-xl mx-auto">
          The manifesto behind OmniBrain — an open-source AI platform
          that answers to no one but you.
        </p>
        <div className="mt-8 text-xs text-[var(--text-tertiary)]">
          Francesco Stabile · 17 February 2026
        </div>
      </section>

      {/* ── Divider ───────────────────────────────────── */}
      <div className="max-w-3xl mx-auto px-6">
        <div className="h-px bg-gradient-to-r from-transparent via-[var(--border-primary)] to-transparent" />
      </div>

      {/* ── Content ───────────────────────────────────── */}
      <article className="max-w-3xl mx-auto px-6 py-16">
        <div className="prose-manifesto space-y-12">

          {/* —— Why This Exists —— */}
          <section>
            <h2>Why This Exists</h2>
            <p className="first-paragraph">
              Something is happening that most people haven&apos;t noticed yet.
            </p>
            <p>
              The most powerful technology ever created — artificial intelligence — is being
              built behind closed doors. Every major AI system that exists today is owned,
              controlled, and operated by a corporation. Your conversations with ChatGPT train
              OpenAI&apos;s models. Your emails feed Google&apos;s advertising engine. Your Siri
              requests shape Apple&apos;s ecosystem lock-in. Your data, your patterns, your
              relationships, your thoughts — they flow into systems you cannot inspect, cannot
              verify, and cannot control.
            </p>
            <p>
              This was tolerable when AI was a chatbot. You asked it a question, it answered.
              If you didn&apos;t trust it, you closed the tab. No harm done.
            </p>
            <p>But that era is ending.</p>
            <p>
              AI is becoming <strong>agentic</strong>. Within the next few years, AI agents will
              manage your inbox, handle your calendar, negotiate your subscriptions, draft your
              communications, track your finances, and make decisions that affect your daily life.
              This is not speculation. Every major tech company is building this right now.
            </p>
            <p>
              When that happens, the question of <strong>who controls your AI</strong> becomes the
              most important question of your digital life.
            </p>
            <p>
              If your AI agent is made by Google, does it recommend restaurants that paid for
              placement? If your AI agent is made by Apple, does it subtly favor Apple products?
              If your AI agent is made by OpenAI, are your most personal decisions — what you write,
              who you talk to, how you spend your money — being used to train the next model that
              gets sold to enterprises?
            </p>
            <p>
              You will never know. Because the code is closed. The logic is hidden. The interests
              are misaligned.
            </p>
            <blockquote>
              This is not a hypothetical future. This is an inevitability. The only question is
              whether an alternative will exist when people finally realize they need one.
            </blockquote>
            <p>OmniBrain is that alternative.</p>
          </section>

          {/* —— The Principle —— */}
          <section>
            <h2>The Principle</h2>
            <p className="text-2xl sm:text-3xl font-bold text-[var(--text-primary)] leading-snug my-8">
              Your AI must be yours.
            </p>
            <p>This means:</p>
            <ul>
              <li>
                <strong>Your data stays on your machine.</strong> Your emails, contacts, calendar,
                memories, patterns, relationships — they live on hardware you own. Not on a server
                controlled by a corporation with a fiduciary duty to shareholders, not to you.
              </li>
              <li>
                <strong>The code is open.</strong> Every line of logic that decides what&apos;s important,
                what to show you, what to recommend, what to hide — it&apos;s readable, auditable,
                and modifiable by anyone. No hidden algorithms. No black boxes. No &ldquo;trust us.&rdquo;
              </li>
              <li>
                <strong>No conflicts of interest.</strong> Your AI works for you and only you. It has no
                advertisers to please. No ecosystem to promote. No data to harvest. No engagement
                metrics to optimize. Its only objective function is your wellbeing.
              </li>
              <li>
                <strong>You are never locked in.</strong> Your data is in open formats. Your memory,
                your knowledge graph, your patterns — they&apos;re exportable, portable, and yours to
                take anywhere. If a better system appears tomorrow, you can leave today with
                everything you built.
              </li>
            </ul>
            <p>
              These are not features. They are rights. And in the age of AI agents, they are as
              fundamental as the right to privacy, the right to free speech, and the right to own
              property.
            </p>
          </section>

          {/* —— The Precedents —— */}
          <section>
            <h2>The Precedents</h2>
            <p>
              This is not the first time a technology was monopolized and then freed.
            </p>
            <p>
              <strong>Software</strong> was proprietary. IBM, Microsoft, Oracle owned it. Then Richard
              Stallman said &ldquo;software should be free&rdquo; and wrote the GPL. Then Linus Torvalds
              built Linux. Today, Linux runs 96% of the world&apos;s servers, every Android phone, and
              the majority of the world&apos;s infrastructure. The corporations that tried to monopolize
              software now build their empires on top of free software.
            </p>
            <p>
              <strong>Communication</strong> was centralized. Telecom companies owned every wire, every
              protocol, every message. Then the open internet happened. Then email — an open protocol
              that no one owns — became the backbone of global communication. The corporations adapted.
              They didn&apos;t win.
            </p>
            <p>
              <strong>Money</strong> was controlled by banks and governments. Then Satoshi Nakamoto
              published a whitepaper and built Bitcoin. Whether you believe in cryptocurrency or not, the
              idea that money can exist without institutional gatekeepers changed the financial system
              permanently.
            </p>
            <p>
              <strong>AI is next.</strong> Today, AI is where software was in 1983, where communication
              was in 1990, where money was in 2008. Monopolized, centralized, controlled. But the pattern
              is always the same: a closed system creates value, the value creates dependency, the
              dependency creates abuse, and then an open alternative emerges that cannot be stopped.
            </p>
            <p>
              OmniBrain is not an attempt to compete with Google, OpenAI, or Anthropic on their terms.
              It is an attempt to make the question irrelevant — by giving every person on Earth the
              ability to own, control, and trust their own AI.
            </p>
          </section>

          {/* —— Who This Is For —— */}
          <section>
            <h2>Who This Is For</h2>
            <p>
              <strong>Today:</strong> developers, self-hosters, privacy advocates, people who run Home
              Assistant and Nextcloud, people who choose Signal over WhatsApp, people who believe in
              open source not as a business strategy but as a moral position.
            </p>
            <p>
              <strong>Tomorrow:</strong> everyone. Because once the first scandal hits — once people
              discover that their AI agent was recommending products because a company paid for it, or
              that their private conversations were used to train a model — the mainstream will want
              what we&apos;ve already built.
            </p>
            <p>We build for the first group. The second group comes to us.</p>
          </section>

          {/* —— The Promise —— */}
          <section>
            <h2>The Promise</h2>
            <p>OmniBrain will always be:</p>
            <ul>
              <li>
                <strong>Free.</strong> The core will never be behind a paywall. Ever.
              </li>
              <li>
                <strong>Open.</strong> MIT license. Every line of code, every algorithm, every
                decision rule — readable and verifiable.
              </li>
              <li>
                <strong>Local.</strong> Your data on your machine by default. Cloud is opt-in,
                never required.
              </li>
              <li>
                <strong>Private.</strong> Zero telemetry. Zero analytics. Zero data collection.
                The user is never the product.
              </li>
              <li>
                <strong>Honest.</strong> When OmniBrain calls an external service (like a cloud LLM
                for text generation), it tells you exactly what data leaves your machine and where
                it goes. No silent data flows. Full transparency.
              </li>
            </ul>
            <p>
              This is not a business strategy. It is a constitution. It does not change with market
              conditions, investor pressure, or growth targets. It is the foundation on which everything
              else is built.
            </p>
          </section>
        </div>
      </article>

      {/* ── CTA ───────────────────────────────────────── */}
      <section className="border-t border-[var(--border-primary)]">
        <div className="max-w-3xl mx-auto px-6 py-20 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold text-[var(--text-primary)] mb-4">
            Ready to own your AI?
          </h2>
          <p className="text-[var(--text-secondary)] mb-8 max-w-md mx-auto">
            Install OmniBrain in 2 minutes. Free, open-source, yours forever.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="https://github.com/OmniBrain-Team/omnibrain"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-[var(--brand-primary)] text-white font-semibold hover:bg-[var(--brand-hover)] transition-colors"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
              </svg>
              View on GitHub
            </a>
            <a
              href="/"
              className="inline-flex items-center gap-2 px-8 py-3 rounded-xl border border-[var(--border-primary)] text-[var(--text-primary)] font-semibold hover:bg-[var(--bg-secondary)] transition-colors"
            >
              Open Dashboard
            </a>
          </div>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────── */}
      <footer className="border-t border-[var(--border-primary)] py-8">
        <div className="max-w-3xl mx-auto px-6 text-center text-xs text-[var(--text-tertiary)]">
          <p>
            OmniBrain is open-source software released under the MIT License.
          </p>
          <p className="mt-2">
            © {new Date().getFullYear()} Francesco Stabile &amp; contributors.
          </p>
        </div>
      </footer>
    </div>
  );
}

/* ── Share Buttons (client island) ───────────────────────── */

function ShareButtons() {
  return (
    <div className="flex items-center gap-1">
      {/* Twitter/X */}
      <a
        href="https://twitter.com/intent/tweet?text=Your%20AI%20must%20be%20yours.%20Read%20the%20OmniBrain%20manifesto.&url=https://omnibrain.dev/manifesto"
        target="_blank"
        rel="noopener noreferrer"
        className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
        aria-label="Share on X"
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      </a>
      {/* LinkedIn */}
      <a
        href="https://www.linkedin.com/sharing/share-offsite/?url=https://omnibrain.dev/manifesto"
        target="_blank"
        rel="noopener noreferrer"
        className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
        aria-label="Share on LinkedIn"
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
        </svg>
      </a>
      {/* Hacker News */}
      <a
        href="https://news.ycombinator.com/submitlink?u=https://omnibrain.dev/manifesto&t=Your%20AI%20Must%20Be%20Yours%20%E2%80%94%20The%20OmniBrain%20Manifesto"
        target="_blank"
        rel="noopener noreferrer"
        className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
        aria-label="Share on Hacker News"
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M0 0v24h24V0H0zm12.8 14.4v5.2h-1.6v-5.2L7 4.8h1.8l3.2 6 3.2-6H17l-4.2 9.6z" />
        </svg>
      </a>
    </div>
  );
}
