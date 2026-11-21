// SOLO SERVIDOR: lo llama la página pública /a/[id] (componente de servidor). No importar desde
// componentes de cliente. Lee API_INTERNAL_URL (por defecto el backend local).
import { cache } from "react";
import type { PublicAlert } from "@/shared/api/types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type PublicAlertResult =
  | { kind: "ok"; alert: PublicAlert }
  | { kind: "not-found" }
  | { kind: "error" };

/** Ficha pública reducida de una alerta (sin autenticación). Deduplicada por solicitud. */
export const getPublicAlert = cache(async (id: string): Promise<PublicAlertResult> => {
  if (!UUID.test(id)) return { kind: "not-found" };
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/public/alerts/${id}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (res.status === 404) return { kind: "not-found" };
    if (!res.ok) return { kind: "error" };
    return { kind: "ok", alert: (await res.json()) as PublicAlert };
  } catch {
    return { kind: "error" };
  }
});
