import type { AuthChangeEvent, Session } from "@supabase/supabase-js";
import { getSupabase } from "@/shared/supabase/client";

export interface SessionState {
  status: "loading" | "authed" | "anon";
  session: Session | null;
  /** true si la sesión nació de un enlace de recuperación de contraseña (evento PASSWORD_RECOVERY). */
  recovery: boolean;
}

const LOADING: SessionState = { status: "loading", session: null, recovery: false };

let state: SessionState = LOADING;
let started = false;
const listeners = new Set<() => void>();

function publish(event: AuthChangeEvent, session: Session | null): void {
  const recovery = event === "PASSWORD_RECOVERY" || (state.recovery && event !== "SIGNED_OUT");
  state = session
    ? { status: "authed", session, recovery }
    : { status: "anon", session: null, recovery: false };
  listeners.forEach((notify) => notify());
}

function start(): void {
  if (started) return;
  started = true;
  // Emite INITIAL_SESSION al suscribirse y luego cada login, logout y refresco de token.
  // PASSWORD_RECOVERY llega antes que INITIAL_SESSION cuando se abre un enlace de recuperación.
  getSupabase().auth.onAuthStateChange((event, session) => publish(event, session));
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
