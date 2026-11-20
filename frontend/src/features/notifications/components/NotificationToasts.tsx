"use client";

import { useNotificationFeed } from "../hooks/useNotificationFeed";

/** Avisos de nuevas notificaciones (Realtime). La región anuncia los cambios a lectores de pantalla. */
export function NotificationToasts() {
  const { items, dismiss } = useNotificationFeed();
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className="toast">
          <p>
            <strong>Nueva alerta.</strong> {item.content}
          </p>
          <button type="button" onClick={() => dismiss(item.id)} aria-label="Cerrar aviso">
            Cerrar
          </button>
        </div>
      ))}
    </div>
  );
}
