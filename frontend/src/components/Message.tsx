import { useState, type ReactNode } from "react";
import type { Hit } from "../api/types";

export type Turn = {
  role: "user" | "assistant";
  content: string;
  hits?: Hit[];
  streaming?: boolean;
  error?: string | null;
};

export function Message({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="msg-role">YOU</div>
        <div className="msg-body">{turn.content}</div>
      </div>
    );
  }

  const knownDois = new Set((turn.hits ?? []).map((h) => h.doi));

  return (
    <div className="msg msg-assistant">
      <div className="msg-body">
        {turn.content
          ? renderMarkdown(turn.content, knownDois)
          : turn.streaming && (
              <span className="streaming-status">retrieving · embedding · ranking</span>
            )}
        {turn.streaming && turn.content && <span className="cursor" />}
      </div>
      {turn.error && <div className="error">{turn.error}</div>}
      {turn.hits && turn.hits.length > 0 && <SourcesPanel hits={turn.hits} />}
    </div>
  );
}

type Block =
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[]; start: number };

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { kind: "ul"; items: string[] } | { kind: "ol"; items: string[]; start: number } | null = null;

  const flushPara = () => {
    if (para.length) {
      blocks.push({ kind: "p", text: para.join(" ") });
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushPara();
      flushList();
      continue;
    }
    const ul = line.match(/^[-*]\s+(.*)/);
    const ol = line.match(/^(\d+)\.\s+(.*)/);
    if (ul) {
      flushPara();
      if (!list || list.kind !== "ul") {
        flushList();
        list = { kind: "ul", items: [] };
      }
      list.items.push(ul[1]);
    } else if (ol) {
      flushPara();
      if (!list || list.kind !== "ol") {
        flushList();
        list = { kind: "ol", items: [], start: parseInt(ol[1]) };
      }
      list.items.push(ol[2]);
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();

  const merged: Block[] = [];
  for (const b of blocks) {
    const prev = merged[merged.length - 1];
    if (prev && (b.kind === "ul" || b.kind === "ol") && prev.kind === b.kind) {
      (prev as { items: string[] }).items.push(...b.items);
    } else {
      merged.push(b);
    }
  }

  // Fix ol start indices so items interspersed with paragraphs number sequentially.
  // e.g. "1. A\n\nparagraph\n\n2. B" produces two <ol> blocks; we set start=1 and start=2.
  let olCount = 0;
  for (const b of merged) {
    if (b.kind === "ol") {
      b.start = olCount + 1;
      olCount += b.items.length;
    } else if (b.kind === "ul") {
      olCount = 0;
    }
  }

  return merged;
}

function renderMarkdown(text: string, knownDois: Set<string>): ReactNode {
  const blocks = parseBlocks(text);
  return blocks.map((b, i) => {
    if (b.kind === "p") return <p key={i}>{renderInline(b.text, knownDois)}</p>;
    if (b.kind === "ul")
      return (
        <ul key={i}>
          {b.items.map((it, j) => <li key={j}>{renderInline(it, knownDois)}</li>)}
        </ul>
      );
    return (
      <ol key={i} start={b.start}>
        {b.items.map((it, j) => <li key={j}>{renderInline(it, knownDois)}</li>)}
      </ol>
    );
  });
}

function renderInline(text: string, knownDois: Set<string>): ReactNode {
  const parts: ReactNode[] = [];
  let key = 0;
  // Pattern: DOI citation, **bold**, *em*, `code`
  const re = /\[DOI:([^\]]+)\]|\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      const doi = m[1].trim();
      const isKnown = knownDois.has(doi);
      parts.push(
        <a
          key={`k${key++}`}
          className={`doi-cite ${isKnown ? "" : "unknown"}`}
          href={`https://doi.org/${doi}`}
          target="_blank"
          rel="noreferrer"
          title={isKnown ? "Cited from retrieved sources" : "DOI not in retrieved set"}
        >
          {doi}
        </a>,
      );
    } else if (m[2] !== undefined) {
      parts.push(<strong key={`k${key++}`}>{m[2]}</strong>);
    } else if (m[3] !== undefined) {
      parts.push(<code key={`k${key++}`}>{m[3]}</code>);
    } else if (m[4] !== undefined) {
      parts.push(<em key={`k${key++}`}>{m[4]}</em>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function SourcesPanel({ hits }: { hits: Hit[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setOpen((v) => !v)}>
        <span>{open ? "▾" : "▸"}</span>
        <span>
          {hits.length} SOURCE{hits.length === 1 ? "" : "S"}
        </span>
      </button>
      {open &&
        hits.map((h, i) => <SourceRow key={`${h.doi}-${i}`} hit={h} />)}
    </div>
  );
}

// Trim a raw text chunk to start at the first complete sentence.
// Vector DB chunks often begin mid-sentence; this finds the first capital-letter
// sentence start and prepends an ellipsis to signal the cut.
function trimToSentence(raw: string): { text: string; trimmed: boolean } {
  const t = raw.trim();
  if (/^[A-Z"'(\[]/.test(t)) return { text: t, trimmed: false };
  const m = t.match(/[.!?]\s+([A-Z])/);
  if (m && m.index !== undefined) {
    return { text: t.slice(m.index + m[0].length - 1), trimmed: true };
  }
  return { text: t, trimmed: true };
}

function SourceRow({ hit }: { hit: Hit }) {
  const { text: displayText, trimmed } = trimToSentence(hit.text);
  return (
    <article className="source">
      <div className="source-meta">
        <span className="source-chip section">{hit.section || "—"}</span>
        <span className="source-chip">{hit.source}</span>
        {hit.subject && <span className="source-chip">{hit.subject}</span>}
        {hit.posted_date && <span className="source-chip">{hit.posted_date}</span>}
        <span className="source-chip">{hit.score.toFixed(3)}</span>
      </div>
      <div className="source-title">
        <a href={`https://doi.org/${hit.doi}`} target="_blank" rel="noreferrer">
          {hit.title || hit.doi}
        </a>
      </div>
      {hit.authors && <div className="source-authors">{hit.authors}</div>}
      <div className="source-text">
        {trimmed && <span className="source-text-lead-ellipsis">… </span>}
        {displayText}
      </div>
    </article>
  );
}
