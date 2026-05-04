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

export function ChatView() {
  const [filters, setFilters] = useState<FilterState>(defaultFilterState());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    streamRef.current?.scrollTo({
      top: streamRef.current.scrollHeight,
      behavior: "smooth",
    });
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
        { query: q, conversation_id: conversationId ?? undefined, ...filtersToReq(filters) },
        (ev) => {
          if (ev.event === "conversation") setConversationId(ev.data.conversation_id);
          else if (ev.event === "hits") patchAssistant({ hits: ev.data as Hit[] });
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
      <div className="chat-stream" ref={streamRef}>
        {turns.map((t, i) => <Message key={i} turn={t} />)}
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
