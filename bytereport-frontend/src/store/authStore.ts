import { create } from "zustand";
import { supabase } from "@/lib/supabase";

interface User {
  id: string;
  email: string;
  name?: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  needsEmailConfirmation: boolean;
  isReady: boolean;  // true after init() resolves the first getSession()
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  init: () => Promise<void>;
}

function toUser(u: { id: string; email?: string | null; user_metadata?: Record<string, unknown> }, name?: string): User {
  return { id: u.id, email: u.email ?? "", name: (u.user_metadata?.name as string | undefined) ?? name };
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: false,
  error: null,
  needsEmailConfirmation: false,
  isReady: false,

  init: async () => {
    const { data } = await supabase.auth.getSession();
    if (data.session?.user) {
      localStorage.setItem("br_token", data.session.access_token);
      set({ user: toUser(data.session.user), isReady: true });
    } else {
      set({ isReady: true });
    }
    supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        localStorage.setItem("br_token", session.access_token);
        set({ user: toUser(session.user), isReady: true });
      } else {
        localStorage.removeItem("br_token");
        set({ user: null, isReady: true });
      }
    });
  },

  login: async (email, password) => {
    set({ loading: true, error: null });
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      set({ loading: false, error: error.message });
      return;
    }
    // signInWithPassword always returns user + session when error is null
    localStorage.setItem("br_token", data.session.access_token);
    set({ user: toUser(data.user), loading: false });
  },

  register: async (email, password, name) => {
    set({ loading: true, error: null, needsEmailConfirmation: false });

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { name } },
    });

    if (error) {
      set({ loading: false, error: error.message });
      return;
    }

    // Case 1: data.user is null — email already registered.
    // Supabase intentionally returns null (no error) to prevent email enumeration.
    // Treat identically to "check your email" so we don't reveal whether the address exists.
    if (!data.user) {
      set({ loading: false, needsEmailConfirmation: true });
      return;
    }

    // Case 2: user exists but no session — email confirmation required.
    if (!data.session) {
      set({ loading: false, needsEmailConfirmation: true });
      return;
    }

    // Case 3: session present — email confirmation disabled in Supabase dashboard.
    // User is immediately logged in.
    localStorage.setItem("br_token", data.session.access_token);
    set({ user: toUser(data.user, name), loading: false });
  },

  logout: async () => {
    await supabase.auth.signOut();
    localStorage.removeItem("br_token");
    set({ user: null, needsEmailConfirmation: false });
  },
}));
