import { useEffect, useState } from "react";
import { ChatView } from "./components/ChatView";
import { AuthButton } from "./components/AuthButton";
import { Sidebar } from "./components/Sidebar";
import type { User } from "./api/types";

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [selectedConvId, setSelectedConvId] = useState<number | null>(null);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const fetchUser = () => {
    fetch("/auth/me")
      .then((r) => r.json())
      .then((d) => setUser(d.user ?? null))
      .catch(() => setUser(null));
  };

  useEffect(() => { fetchUser(); }, []);

  const handleConversationCreated = (id: number) => {
    setSelectedConvId(id);
    setSidebarRefreshKey((k) => k + 1);
  };

  return (
    <div className="app">
      <Sidebar
        user={user}
        selectedConvId={selectedConvId}
        onSelectConv={setSelectedConvId}
        onNewChat={() => setSelectedConvId(null)}
        refreshKey={sidebarRefreshKey}
        isOpen={sidebarOpen}
      />
      <div className="app-main">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarOpen((o) => !o)}
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          {sidebarOpen ? "‹" : "›"}
        </button>
        <div className="auth-corner">
          <AuthButton user={user} onAuthChange={() => { fetchUser(); setSidebarRefreshKey((k) => k + 1); }} />
        </div>
        <main className="chat-shell">
          <ChatView
            selectedConvId={selectedConvId}
            onConversationCreated={handleConversationCreated}
          />
        </main>
      </div>
    </div>
  );
}
