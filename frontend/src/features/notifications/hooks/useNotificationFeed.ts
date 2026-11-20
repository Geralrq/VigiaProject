"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "@/features/auth/hooks/useSession";
import { getSupabase } from "@/shared/supabase/client";

export interface IncomingNotification {
  id: string;
  content: string;
}

interface NotificationRow {
  id: string;
  contenido: string;
  canal: string;
}

/**
 * Suscripción a Supabase Realtime sobre `notifications` con la sesión del usuario: la RLS
 * (usuario = auth.uid()) hace que solo lleguen las propias. Al llegar una, la agrega a la
 * lista de avisos y refresca las alertas.
 */
export function useNotificationFeed() {
  const queryClient = useQueryClient();
  const { session } = useSession();
  const userId = session?.user.id;
  const token = session?.access_token;
  const [items, setItems] = useState<IncomingNotification[]>([]);

  useEffect(() => {
    if (!userId || !token) return;
    const supabase = getSupabase();
    void supabase.realtime.setAuth(token); // Realtime evalúa la RLS con el JWT del usuario
    const channel = supabase
      .channel(`notifications:${userId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "notifications", filter: `usuario=eq.${userId}` },
        (payload) => {
          const row = payload.new as NotificationRow;
          if (row.canal !== "WEB") return; // los demás canales no son avisos en pantalla
          setItems((current) => [...current, { id: row.id, content: row.contenido }]);
          void queryClient.invalidateQueries({ queryKey: ["alerts"] });
          void queryClient.invalidateQueries({ queryKey: ["anomalies"] });
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [userId, token, queryClient]);

  const dismiss = useCallback(
    (id: string) => setItems((current) => current.filter((item) => item.id !== id)),
    [],
  );

  return { items, dismiss };
}
