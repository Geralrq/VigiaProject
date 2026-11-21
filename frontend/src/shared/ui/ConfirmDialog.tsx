"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Diálogo de confirmación accesible sobre <dialog> modal nativo: atrapa el foco, el resto de la
 * página queda inerte, Esc lo cierra y el foco vuelve al botón que lo abrió. El foco inicial
 * cae en «Cancelar» (la opción segura).
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancelar",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault(); // Esc: lo cierra el estado del padre, no el navegador
        if (!busy) onCancel();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel(); // clic en el fondo
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <div id={descriptionId} className="dialog-body">
        {children}
      </div>
      <div className="dialog-actions">
        <button type="button" onClick={onCancel} disabled={busy} autoFocus>
          {cancelLabel}
        </button>
        <button type="button" className="primary" onClick={onConfirm} disabled={busy} aria-busy={busy}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
