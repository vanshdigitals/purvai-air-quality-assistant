import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Info,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";

import { AqiCategoryChip } from "../../components/AqiCategoryChip";
import {
  ApiError,
  deleteConversations,
  fetchConversations,
  fetchHousehold,
  postChat,
  type ChatResponse,
} from "../../lib/api";
import { formatHoursOld, formatIstTimeWithZone } from "../../lib/datetime";

const SUGGESTED_QUESTIONS: readonly string[] = [
  "Can my child play outside at 5 pm?",
  "Should I open the windows now?",
  "Is a morning walk okay today?",
  "Which mask should I use?",
];

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  userText?: string;
  reply?: ChatResponse;
  historyText?: string;
  historyGeneratedBy?: "user" | "gemini" | "groq" | "template";
}

function sourceFooterText(source: string): string {
  if (source === "gemini") return "Worded by Gemini";
  if (source === "groq") return "Worded by Groq";
  return "Standard advice";
}

export default function AskPage() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [sessionTurns, setSessionTurns] = useState<ChatTurn[]>([]);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  const composerRef = useRef<HTMLTextAreaElement>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const isOnline = typeof window !== "undefined" ? window.navigator.onLine : true;

  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  const saveChatEnabled = Boolean(householdQuery.data?.settings.save_chat);

  const historyQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
    enabled: Boolean(householdQuery.data && saveChatEnabled),
    retry: false,
  });

  const chatMutation = useMutation({
    mutationFn: (message: string) => postChat(message),
    onSuccess: (reply, sentMessage) => {
      setLastFailedMessage(null);
      const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setSessionTurns((prev) => [
        ...prev,
        { id: `u-${suffix}`, role: "user", userText: sentMessage },
        { id: `a-${suffix}`, role: "assistant", reply },
      ]);
      if (saveChatEnabled) {
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      }
      composerRef.current?.focus();
    },
    onError: (_err, sentMessage) => {
      setLastFailedMessage(sentMessage);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteConversations,
    onSuccess: () => {
      setSessionTurns([]);
      setConfirmDeleteOpen(false);
      queryClient.setQueryData(["conversations"], { messages: [] });
    },
  });

  useEffect(() => {
    if (!confirmDeleteOpen) return;
    const returnTarget = deleteBtnRef.current;
    cancelDeleteRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent | globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setConfirmDeleteOpen(false);
        return;
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      returnTarget?.focus();
    };
  }, [confirmDeleteOpen]);

  const trimmed = draft.trim();
  const charCount = draft.length;
  const overLimit = charCount > 500;
  const canSend = Boolean(trimmed.length > 0 && !overLimit && !chatMutation.isPending && isOnline);

  const sendMessage = (text: string) => {
    const clean = text.trim();
    if (!clean || clean.length > 500 || chatMutation.isPending || !isOnline) {
      return;
    }
    setDraft("");
    chatMutation.mutate(clean);
    composerRef.current?.focus();
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) {
        sendMessage(draft);
      }
    }
  };

  const savedEntries: ChatTurn[] =
    saveChatEnabled && historyQuery.data
      ? historyQuery.data.messages.map((msg) => ({
          id: `saved-${msg.id}`,
          role: msg.role,
          userText: msg.role === "user" ? msg.text : undefined,
          historyText: msg.role === "assistant" ? msg.text : undefined,
          historyGeneratedBy: msg.generated_by,
        }))
      : [];

  // When save_chat is enabled and historyQuery succeeded after a send, savedEntries covers persisted turns;
  // show optimistic sessionTurns only while save_chat is off or before saved history catches up.
  const displayedTurns: ChatTurn[] = saveChatEnabled
    ? savedEntries.length > 0
      ? savedEntries
      : sessionTurns
    : sessionTurns;

  const errorText = (() => {
    const err = chatMutation.error;
    if (err instanceof ApiError && err.status === 429) {
      const secs = err.retryAfterSeconds ?? 60;
      return `Too many questions. Try again in ${secs} seconds.`;
    }
    if (err instanceof ApiError) {
      return err.message;
    }
    return "Could not answer your question right now.";
  })();

  const hasHistoryToDelete = saveChatEnabled && displayedTurns.length > 0;

  return (
    <div className="mx-auto max-w-[720px] space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1>Ask Purvai</h1>
          <p className="text-text-2">
            Evidence-grounded answers using your household rules and local air readings.
          </p>
        </div>

        {hasHistoryToDelete && (
          <button
            ref={deleteBtnRef}
            type="button"
            onClick={() => setConfirmDeleteOpen(true)}
            className="purvai-btn purvai-btn-danger-subtle"
          >
            <Trash2 size={16} aria-hidden />
            <span>Delete chat history</span>
          </button>
        )}
      </div>

      {/* History setting notice */}
      {householdQuery.data && !saveChatEnabled && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-[6px] border border-border bg-subtle px-4 py-2.5 text-sm text-text-2"
        >
          <span>Chat history is off. Nothing is saved.</span>
          <Link to="/settings" className="font-medium text-primary underline underline-offset-4">
            Settings
          </Link>
        </div>
      )}

      {/* Empty state & suggested questions */}
      {displayedTurns.length === 0 && !chatMutation.isPending && (
        <section className="purvai-card space-y-4 p-6">
          <div className="flex items-start gap-3">
            <MessageSquare size={20} className="mt-0.5 shrink-0 text-primary" aria-hidden />
            <div className="space-y-1">
              <h2 className="text-lg font-semibold">Ask about the air today</h2>
              <p className="text-sm text-text-2">
                Choose a common question below or type your own (up to 500 characters).
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2.5">
            {SUGGESTED_QUESTIONS.map((question) => (
              <button
                key={question}
                type="button"
                disabled={!isOnline || chatMutation.isPending}
                onClick={() => sendMessage(question)}
                className="purvai-btn purvai-btn-secondary h-auto py-2 text-left"
              >
                {question}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Message thread */}
      <div role="log" aria-label="Conversation" className="space-y-4">
        {displayedTurns.map((turn) => {
          if (turn.role === "user") {
            return (
              <div
                key={turn.id}
                className="ml-auto max-w-[85%] rounded-[10px] border border-border bg-subtle px-4 py-3 text-sm text-text"
              >
                <div className="mb-1 text-xs font-medium text-muted">You</div>
                <p className="whitespace-pre-wrap">{turn.userText}</p>
              </div>
            );
          }

          if (turn.historyText !== undefined) {
            return (
              <article key={turn.id} className="purvai-card space-y-2 bg-surface p-5">
                <p className="whitespace-pre-wrap text-text">{turn.historyText}</p>
                <p className="text-xs text-muted">
                  {sourceFooterText(turn.historyGeneratedBy ?? "template")}
                </p>
              </article>
            );
          }

          const reply = turn.reply;
          if (!reply) return null;

          const observedLabel = formatIstTimeWithZone(reply.observed_at);

          return (
            <article
              key={turn.id}
              aria-live="polite"
              className="purvai-card space-y-4 bg-surface p-5"
            >
              {reply.note && (
                <div
                  role="status"
                  className="flex items-center gap-2 rounded-[6px] border border-border bg-info-tint px-3 py-2 text-sm text-info"
                >
                  <Info size={16} className="shrink-0" aria-hidden />
                  <span>{reply.note}</span>
                </div>
              )}

              {reply.out_of_scope && (
                <p className="text-sm font-medium text-text-2">
                  I can help with air quality and keeping your household safer.
                </p>
              )}

              <p className="whitespace-pre-wrap text-text">{reply.answer}</p>

              {/* Data chips from data_cited */}
              <div className="flex flex-wrap items-center gap-2">
                {(reply.data_cited.includes("aqi") || reply.data_cited.includes("category")) && (
                  <div className="inline-flex items-center gap-2 rounded-full border border-border bg-subtle px-2.5 py-1 text-xs font-medium text-text">
                    <span className="tabular-data">AQI {reply.aqi}</span>
                    <AqiCategoryChip category={reply.category} />
                  </div>
                )}

                {reply.data_cited.includes("source") && (
                  <span className="rounded-full border border-border bg-subtle px-2.5 py-1 text-xs font-medium text-text-2">
                    {reply.source_label === "Modelled" ? "Modelled estimate" : reply.source_label}
                  </span>
                )}

                <span className="tabular-data rounded-full border border-border bg-subtle px-2.5 py-1 text-xs font-medium text-text-2">
                  {observedLabel}
                </span>

                {reply.stale && (
                  <span className="rounded-full border border-warning bg-warning-tint px-2.5 py-1 text-xs font-medium text-warning">
                    {formatHoursOld(reply.age_minutes)} old
                  </span>
                )}

                {reply.data_cited.includes("grap") && reply.grap_stage && (
                  <span className="rounded-full border border-border bg-info-tint px-2.5 py-1 text-xs font-medium text-info">
                    GRAP Stage {reply.grap_stage}
                  </span>
                )}
              </div>

              {reply.recommendations.length > 0 && (
                <ul className="space-y-2 border-t border-border pt-3">
                  {reply.recommendations.map((rec) => (
                    <li
                      key={rec.action_id}
                      className="flex items-start justify-between gap-3 rounded-[6px] border border-border bg-subtle px-3 py-2.5 text-sm"
                    >
                      <div className="flex items-start gap-2">
                        <ShieldCheck
                          size={16}
                          className="mt-0.5 shrink-0 text-accent"
                          aria-hidden
                        />
                        <div>
                          <div className="font-medium text-text">{rec.title}</div>
                          <div className="text-xs text-text-2">{rec.why}</div>
                        </div>
                      </div>
                      <span className="shrink-0 rounded-full border border-border bg-surface px-2 py-0.5 text-xs text-text-2">
                        {rec.tag === "ai_wording" ? "AI wording" : "Rule"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {reply.needs_doctor_note && (
                <div
                  role="status"
                  className="flex items-start gap-2 rounded-[6px] border border-border bg-info-tint px-3 py-2.5 text-sm text-info"
                >
                  <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
                  <span>
                    Consult a doctor if breathing discomfort, wheezing, or chest symptoms persist.
                  </span>
                </div>
              )}

              <p className="text-xs text-muted">{sourceFooterText(reply.generated_by)}</p>
            </article>
          );
        })}

        {chatMutation.isPending && (
          <div aria-busy="true" className="purvai-card space-y-2 bg-surface p-5">
            <div className="text-sm text-text-2">Checking the air data…</div>
            <div className="h-4 w-3/4 animate-pulse rounded bg-subtle" />
            <div className="h-4 w-1/2 animate-pulse rounded bg-subtle" />
          </div>
        )}
      </div>

      {/* Error banner */}
      {chatMutation.isError && (
        <div
          role="alert"
          aria-live="assertive"
          className="purvai-card flex flex-wrap items-center justify-between gap-3 border-danger bg-danger-tint p-4 text-sm text-danger"
        >
          <div className="flex items-center gap-2">
            <AlertCircle size={18} className="shrink-0" aria-hidden />
            <span>{errorText}</span>
          </div>
          {lastFailedMessage && (
            <button
              type="button"
              onClick={() => sendMessage(lastFailedMessage)}
              className="purvai-btn purvai-btn-tertiary"
            >
              <RefreshCw size={16} aria-hidden />
              <span>Retry</span>
            </button>
          )}
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage(draft);
        }}
        className="purvai-card space-y-3 p-5"
      >
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="ask-composer" className="text-sm font-medium text-text">
            Ask a question
          </label>
          <span
            className={`tabular-data text-xs ${
              overLimit ? "font-semibold text-danger" : "text-muted"
            }`}
          >
            {charCount}/500
          </span>
        </div>

        <textarea
          ref={composerRef}
          id="ask-composer"
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleComposerKeyDown}
          placeholder="Ask about outdoor play, windows, exercise, or masks..."
          aria-describedby={overLimit ? "ask-limit-error" : "ask-disclaimer"}
          className={`w-full rounded-[6px] border bg-surface p-3 text-base text-text ${
            overLimit ? "border-danger" : "border-input-border"
          }`}
        />

        {overLimit && (
          <p id="ask-limit-error" className="text-xs text-danger">
            Questions must be 500 characters or fewer.
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p id="ask-disclaimer" className="text-xs text-muted">
            Purvai gives general guidance, not medical advice.
          </p>

          <button type="submit" disabled={!canSend} className="purvai-btn purvai-btn-primary">
            <Send size={16} aria-hidden />
            <span>Send</span>
          </button>
        </div>
      </form>

      {/* Delete confirmation dialog */}
      {confirmDeleteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-history-title"
            className="purvai-card w-full max-w-[440px] space-y-4 bg-surface p-6"
          >
            <h2 id="delete-history-title" className="text-lg font-semibold text-text">
              Delete saved chat history?
            </h2>
            <p className="text-sm text-text-2">
              This removes all saved Ask Purvai questions and replies from your device database.
            </p>
            <div className="flex flex-wrap justify-end gap-3 pt-2">
              <button
                ref={cancelDeleteRef}
                type="button"
                onClick={() => setConfirmDeleteOpen(false)}
                className="purvai-btn purvai-btn-tertiary"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate()}
                className="purvai-btn purvai-btn-danger"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
