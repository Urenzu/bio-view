import { useEffect, useState } from "react";
import type { User } from "../api/types";

type ConvSummary = {
  id: number;
  title: string;
  created_at: string;
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

  useEffect(() => {
    fetch("/conversations")
      .then((r) => r.ok ? r.json() : [])
      .then(setConvs)
      .catch(() => setConvs([]));
  }, [refreshKey, user]);

  const groups = groupByDate(convs);

  return (
    <aside className={`sidebar ${isOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <div className="sidebar-top">
        <button className="sidebar-new-btn" onClick={onNewChat}>
          + New chat
        </button>
      </div>

      <nav className="sidebar-convs">
        {user === null && (
          <p className="sidebar-hint">Sign in to save conversations.</p>
        )}
        {user && convs.length === 0 && (
          <p className="sidebar-hint">No conversations yet.</p>
        )}
        {groups.map(({ label, items }) => (
          <div key={label} className="sidebar-group">
            <div className="sidebar-group-label">{label}</div>
            {items.map((c) => (
              <button
                key={c.id}
                className={`sidebar-conv-item ${selectedConvId === c.id ? "active" : ""}`}
                onClick={() => onSelectConv(c.id)}
                title={c.title}
              >
                {c.title}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
