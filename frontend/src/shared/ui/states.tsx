"use client";

import type { ReactNode } from "react";
import { Icon } from "./icons/Icon";
import type { IconName } from "./icons/paths";
import { UiIcon } from "./icons/ui";

/**
 * Esqueleto de carga. Las barras son decorativas; el lector de pantalla oye solo `label`.
 * `lines` filas de texto, o `variant="list"` para filas de lista, o "block" para un bloque.
 */
export function Skeleton({
  label,
  lines = 3,
  variant = "text",
}: {
  label: string;
  lines?: number;
  variant?: "text" | "list" | "block";
}) {
  return (
    <div className={`skeleton skeleton-${variant}`} role="status">
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: variant === "block" ? 1 : lines }, (_, i) => (
        <span key={i} className="skeleton-bar" aria-hidden="true" />
      ))}
    </div>
  );
}

/** Ilustración simple: el icono dentro de una geocerca punteada, sobre la línea del horizonte. */
function Illustration({ icon }: { icon: IconName }) {
  return (
    <svg className="illustration" viewBox="0 0 120 72" aria-hidden="true" focusable="false">
      <circle cx="60" cy="34" r="26" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 4" />
      <path d="M8 62h104M30 68h60" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
      <foreignObject x="44" y="18" width="32" height="32">
        <Icon name={icon} size={32} />
      </foreignObject>
    </svg>
  );
}

/** Estado vacío: qué significa y qué se puede hacer. */
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: IconName;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <Illustration icon={icon} />
      <p className="empty-title">{title}</p>
      {children && <div className="empty-body">{children}</div>}
      {action && <div className="actions">{action}</div>}
    </div>
  );
}

/** Error con la causa y una acción de reintento. */
export function ErrorState({
  message,
  onRetry,
  children,
}: {
  message: string;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="error-state" role="alert">
      <p>
        <UiIcon name="aviso" size={18} /> <span>{message}</span>
      </p>
      <div className="actions">
        {onRetry && (
          <button type="button" onClick={onRetry}>
            <UiIcon name="reintentar" size={18} /> Reintentar
          </button>
        )}
        {children}
      </div>
    </div>
  );
}
