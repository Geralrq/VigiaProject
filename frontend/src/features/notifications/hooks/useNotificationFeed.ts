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
 *
 * Depende solo del id de usuario: supabase-js renueva el JWT de Realtime por su cuenta, así que
 * el refresco horario del token no resuscribe el canal.
 */
export function useNotificationFeed() {
  const queryClient = useQueryClient();
  const userId = useSession().session?.user.id;
  const [items, setItems] = useState<IncomingNotification[]>([]);

  useEffect(() => {
    if (!userId) return;
    const supabase = getSupabase();
    let cancelled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled || !data.session) return;
      // Realtime evalúa la RLS con el JWT del usuario: se fija antes de suscribirse.
      void supabase.realtime.setAuth(data.session.access_token);
      channel = supabase
        .channel(`notifications:${userId}`)
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "public",
            table: "notifications",
            filter: `usuario=eq.${userId}`,
          },
          (payload) => {
            const row = payload.new as NotificationRow;
            if (row.canal !== "WEB") return; // los demás canales no son avisos en pantalla
            setItems((current) => [...current, { id: row.id, content: row.contenido }]);
            void queryClient.invalidateQueries({ queryKey: ["alerts"] });
            void queryClient.invalidateQueries({ queryKey: ["anomalies"] });
          },
        )
        .subscribe();
    });

    return () => {
      cancelled = true;
      if (channel) void supabase.removeChannel(channel);
    };
  }, [userId, queryClient]);

  const dismiss = useCallback(
    (id: string) => setItems((current) => current.filter((item) => item.id !== id)),
    [],
  );

  return { items, dismiss };
}
