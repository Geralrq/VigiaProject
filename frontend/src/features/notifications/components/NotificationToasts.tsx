"use client";

import { UiIcon } from "@/shared/ui/icons/ui";
import { useNotificationFeed } from "../hooks/useNotificationFeed";

/**
 * Avisos de nuevas notificaciones (Realtime). La barra de tiempo los cierra solos a los 10 s;
 * se pausa al pasar el ratón o al enfocar el aviso, y con movimiento reducido no hay cierre
 * automático (el aviso queda hasta que se cierra a mano).
 */
export function NotificationToasts() {
  const { items, dismiss } = useNotificationFeed();
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className="toast">
          <p>
            <strong>Nueva alerta.</strong> {item.content}
          </p>
          <button
            type="button"
            className="icon-button"
            onClick={() => dismiss(item.id)}
            aria-label="Cerrar aviso"
          >
            <UiIcon name="cerrar" />
          </button>
          <span
            className="toast-timer"
            aria-hidden="true"
            onAnimationEnd={() => dismiss(item.id)}
          />
        </div>
      ))}
    </div>
  );
}
