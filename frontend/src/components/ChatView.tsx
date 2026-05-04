import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { streamAsk } from "../api/sse";
import type { AskRequest, Hit } from "../api/types";
import { FilterBar, defaultFilterState, type FilterState } from "./FilterBar";
import { Message, type Turn } from "./Message";

function filtersToReq(f: FilterState): Partial<AskRequest> {
  const out: Partial<AskRequest> = {};
  if (f.subjects.length) out.subjects = f.subjects;
  if (f.date_from) out.date_from = f.date_from;
  if (f.date_to) out.date_to = f.date_to;
  return out;
}

export function ChatView({
  selectedConvId,
  onConversationCreated,
}: {
  selectedConvId: number | null;
  onConversationCreated: (id: number) => void;
}) {
  const [filters, setFilters] = useState<FilterState>(defaultFilterState());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Tracks the conversation currently active in this chat window (may differ
  // from selectedConvId during streaming — we don't want a mid-stream DB reload).
  const activeConvIdRef = useRef<number | null>(null);

  // When the user picks a conversation from the sidebar, load it.
  // When selectedConvId goes null (New chat), clear the view.
  // Skip the load if we just created this conversation ourselves (still streaming).
  useEffect(() => {
    if (selectedConvId === null) {
      activeConvIdRef.current = null;
      setTurns([]);
      return;
    }
    // Already showing this conversation — don't reload (e.g. after creation).
    if (activeConvIdRef.current === selectedConvId) return;

    activeConvIdRef.current = selectedConvId;
    fetch(`/conversations/${selectedConvId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        setTurns(
          data.messages.map((m: { role: string; content: string; hits: Hit[] }) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
            hits: m.hits ?? [],
          }))
        );
      })
      .catch(() => {});
  }, [selectedConvId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const patchAssistant = (patch: Partial<Turn>) =>
    setTurns((ts) => {
      if (!ts.length) return ts;
      const out = ts.slice();
      const i = out.length - 1;
      out[i] = { ...out[i], ...patch };
      return out;
    });

  const appendContent = (delta: string) =>
    setTurns((ts) => {
      if (!ts.length) return ts;
      const out = ts.slice();
      const i = out.length - 1;
      out[i] = { ...out[i], content: out[i].content + delta };
      return out;
    });

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    const q = input.trim();
    if (!q || busy) return;

    setInput("");
    setTurns((t) => [
      ...t,
      { role: "user", content: q },
      { role: "assistant", content: "", hits: [], streaming: true, error: null },
    ]);
    setBusy(true);

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      await streamAsk(
        { query: q, conversation_id: activeConvIdRef.current ?? undefined, ...filtersToReq(filters) },
        (ev) => {
          if (ev.event === "conversation") {
            // Mark as active so the useEffect won't reload when the parent
            // updates selectedConvId with this same id.
            activeConvIdRef.current = ev.data.conversation_id;
            onConversationCreated(ev.data.conversation_id);
          } else if (ev.event === "hits") patchAssistant({ hits: ev.data as Hit[] });
          else if (ev.event === "token") appendContent(ev.data);
          else if (ev.event === "error") patchAssistant({ error: ev.data.message });
        },
        ctrl.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        patchAssistant({ error: (err as Error).message });
      }
    } finally {
      patchAssistant({ streaming: false });
      setBusy(false);
    }
  };

  const stop = () => abortRef.current?.abort();

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  const empty = turns.length === 0;

  return (
    <div className={`chat ${empty ? "is-empty" : ""}`}>
      <div className="chat-stream">
        {turns.map((t, i) => <Message key={i} turn={t} />)}
        <div ref={bottomRef} />
      </div>
      <div className="composer-shell">
        <FilterBar value={filters} onChange={setFilters} />
        <form onSubmit={submit} className="composer">
          <textarea
            placeholder="Query the corpus…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={busy}
          />
          {busy ? (
            <button type="button" className="composer-btn stop" onClick={stop}>
              STOP
            </button>
          ) : (
            <button
              type="submit"
              className="composer-btn"
              disabled={!input.trim()}
            >
              ↵ SEND
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
