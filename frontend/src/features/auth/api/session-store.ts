import type { Session } from "@supabase/supabase-js";
import { getSupabase } from "@/shared/supabase/client";

export interface SessionState {
  status: "loading" | "authed" | "anon";
  session: Session | null;
}

const LOADING: SessionState = { status: "loading", session: null };

let state: SessionState = LOADING;
let started = false;
const listeners = new Set<() => void>();

function publish(session: Session | null): void {
  state = session ? { status: "authed", session } : { status: "anon", session: null };
  listeners.forEach((notify) => notify());
}

function start(): void {
  if (started) return;
  started = true;
  // Emite INITIAL_SESSION al suscribirse y luego cada login, logout y refresco de token.
  getSupabase().auth.onAuthStateChange((_event, session) => publish(session));
}

export function subscribeSession(onChange: () => void): () => void {
  listeners.add(onChange);
  start();
  return () => {
    listeners.delete(onChange);
  };
}

export const getSessionSnapshot = (): SessionState => state;
export const getServerSessionSnapshot = (): SessionState => LOADING;
