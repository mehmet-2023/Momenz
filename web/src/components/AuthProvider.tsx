"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { auth } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthContextValue = {
  me: User | null;
  loading: boolean;
  setMe: (user: User | null) => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  me: null,
  loading: true,
  setMe: () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await auth.me());
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ me, loading, setMe, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
