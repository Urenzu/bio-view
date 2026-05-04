import { useEffect, useRef, useState } from "react";
import type { User } from "../api/types";

type ConvSummary = {
  id: number;
  title: string;
  created_at: string;
  pinned: boolean;
};

function groupByDate(convs: ConvSummary[]): { label: string; items: ConvSummary[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const week = today - 6 * 86400000;

  const groups: Record<string, ConvSummary[]> = {
    Today: [],
    Yesterday: [],
    "This week": [],
    Older: [],
  };

  for (const c of convs) {
    const t = new Date(c.created_at).getTime();
    if (t >= today) groups["Today"].push(c);
    else if (t >= yesterday) groups["Yesterday"].push(c);
    else if (t >= week) groups["This week"].push(c);
    else groups["Older"].push(c);
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}

function ConvItem({
  conv,
  selected,
  onSelect,
  onRename,
  onPin,
}: {
  conv: ConvSummary;
  selected: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onPin: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState(conv.title);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const startEdit = () => {
    setMenuOpen(false);
    setDraft(conv.title);
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== conv.title) onRename(trimmed);
    setEditing(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { setEditing(false); }
  };

  if (editing) {
    return (
      <div className={`sidebar-conv-row ${selected ? "active" : ""} is-editing`}>
        <input
          ref={inputRef}
          className="sidebar-rename-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKeyDown}
          autoFocus
        />
      </div>
    );
  }

  return (
    <div className={`sidebar-conv-row ${selected ? "active" : ""} ${menuOpen ? "menu-open" : ""}`}>
      <div
        className="sidebar-conv-label"
        onClick={onSelect}
        onDoubleClick={startEdit}
      >
        {conv.title}
      </div>
      <div className="sidebar-conv-menu-wrap" ref={menuRef}>
        <button
          className="sidebar-conv-dots"
          onClick={(e) => { e.stopPropagation(); setMenuOpen((o) => !o); }}
          tabIndex={-1}
        >
          ···
        </button>
        {menuOpen && (
          <div className="sidebar-conv-menu">
            <button onClick={startEdit}>Rename</button>
            <button onClick={() => { setMenuOpen(false); onPin(); }}>
              {conv.pinned ? "Unpin" : "Pin"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Sidebar({
  user,
  selectedConvId,
  onSelectConv,
  onNewChat,
  refreshKey,
  isOpen,
}: {
  user: User | null | undefined;
  selectedConvId: number | null;
  onSelectConv: (id: number) => void;
  onNewChat: () => void;
  refreshKey: number;
  isOpen: boolean;
}) {
  const [convs, setConvs] = useState<ConvSummary[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/conversations")
      .then((r) => r.ok ? r.json() : [])
      .then(setConvs)
      .catch(() => setConvs([]));
  }, [refreshKey, user]);

  const patch = (id: number, update: Partial<ConvSummary>) => {
    fetch(`/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }).then((r) => {
      if (r.ok) setConvs((cs) => {
        const updated = cs.map((c) => c.id === id ? { ...c, ...update } : c);
        // Re-sort: pinned first (by original order from server), unpinned by created_at
        return [
          ...updated.filter((c) => c.pinned),
          ...updated.filter((c) => !c.pinned),
        ];
      });
    });
  };

  const openSearch = () => {
    setSearchOpen(true);
    setTimeout(() => searchRef.current?.focus(), 0);
  };

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery("");
  };

  const q = query.trim().toLowerCase();
  const filtered = q ? convs.filter((c) => c.title.toLowerCase().includes(q)) : null;

  const pinned = convs.filter((c) => c.pinned);
  const unpinned = convs.filter((c) => !c.pinned);
  const dateGroups = groupByDate(unpinned);

  const itemProps = (c: ConvSummary) => ({
    key: c.id,
    conv: c,
    selected: selectedConvId === c.id,
    onSelect: () => onSelectConv(c.id),
    onRename: (title: string) => patch(c.id, { title }),
    onPin: () => patch(c.id, { pinned: !c.pinned }),
  });

  return (
    <aside className={`sidebar ${isOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <div className="sidebar-top">
        <button className="sidebar-new-btn" onClick={onNewChat}>
          + New chat
        </button>
        {searchOpen ? (
          <div className="sidebar-search-row">
            <input
              ref={searchRef}
              className="sidebar-search-input"
              placeholder="Search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && closeSearch()}
              onBlur={() => setTimeout(closeSearch, 100)}
            />
          </div>
        ) : (
          <button className="sidebar-search-btn" onClick={openSearch}>
            / Search
          </button>
        )}
      </div>

      <nav className="sidebar-convs">
        {user === null && (
          <p className="sidebar-hint">Sign in to save conversations.</p>
        )}
        {user && convs.length === 0 && (
          <p className="sidebar-hint">No conversations yet.</p>
        )}

        {filtered ? (
          <div className="sidebar-group">
            <div className="sidebar-group-label">{filtered.length} result{filtered.length !== 1 ? "s" : ""}</div>
            {filtered.length === 0
              ? <p className="sidebar-hint">No matches.</p>
              : filtered.map((c) => <ConvItem {...itemProps(c)} />)
            }
          </div>
        ) : (
          <>
            {pinned.length > 0 && (
              <div className="sidebar-group">
                <div className="sidebar-group-label">Pinned</div>
                {pinned.map((c) => <ConvItem {...itemProps(c)} />)}
              </div>
            )}
            {dateGroups.map(({ label, items }) => (
              <div key={label} className="sidebar-group">
                <div className="sidebar-group-label">{label}</div>
                {items.map((c) => <ConvItem {...itemProps(c)} />)}
              </div>
            ))}
          </>
        )}
      </nav>
    </aside>
  );
}
