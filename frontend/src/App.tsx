import { useEffect, useState } from "react";
import { ChatView } from "./components/ChatView";
import { AuthButton } from "./components/AuthButton";
import type { User } from "./api/types";

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  const fetchUser = () => {
    fetch("/auth/me")
      .then((r) => r.json())
      .then((d) => setUser(d.user ?? null))
      .catch(() => setUser(null));
  };

  useEffect(() => { fetchUser(); }, []);

  return (
    <div className="app">
      <div className="auth-corner">
        <AuthButton user={user} onAuthChange={fetchUser} />
      </div>
      <main className="chat-shell">
        <ChatView />
      </main>
    </div>
  );
}
