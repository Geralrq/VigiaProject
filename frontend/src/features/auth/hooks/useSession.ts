"use client";

import { useSyncExternalStore } from "react";
import {
  getServerSessionSnapshot,
  getSessionSnapshot,
  subscribeSession,
  type SessionState,
} from "../api/session-store";

/** Estado de la sesión de Supabase: "loading" hasta que el navegador la restaura. */
export function useSession(): SessionState {
  return useSyncExternalStore(subscribeSession, getSessionSnapshot, getServerSessionSnapshot);
}
