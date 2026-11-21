"use client";

import { useId, useRef, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

export type SheetSnap = "peek" | "half" | "full";
const SNAPS: readonly SheetSnap[] = ["peek", "half", "full"];
const SNAP_LABELS: Record<SheetSnap, string> = {
  peek: "minimizado",
  half: "a media altura",
  full: "expandido",
};

export interface SheetTab {
  id: string;
  label: string;
  icon?: ReactNode;
  content: ReactNode;
}

interface Props {
  label: string;
  tabs: readonly SheetTab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  snap: SheetSnap;
  onSnapChange: (snap: SheetSnap) => void;
}

/**
 * Panel inferior arrastrable (móvil) con pestañas. Se arrastra desde el tirador con el dedo o el
 * ratón y se ancla a tres alturas; el tirador también es un botón: Enter/Espacio cambia de altura
 * y las flechas arriba/abajo suben o bajan. Las pestañas siguen el patrón tablist de ARIA.
 */
export function BottomSheet({ label, tabs, activeTab, onTabChange, snap, onSnapChange }: Props) {
  const id = useId();
  const sheetRef = useRef<HTMLDivElement>(null);
  // Valores transitorios del arrastre en refs: se escribe el transform directo en el DOM
  // (sin re-render por cada pointermove) y el estado solo cambia al soltar.
  const drag = useRef<{ startY: number; startHeight: number; height: number; moved: boolean } | null>(
    null,
  );
  const justDragged = useRef(false); // el click que sigue a un arrastre no cambia de altura

  const step = (delta: 1 | -1) => {
    const next = SNAPS[Math.min(SNAPS.length - 1, Math.max(0, SNAPS.indexOf(snap) + delta))];
    onSnapChange(next);
  };

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    const sheet = sheetRef.current;
    if (!sheet) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    // Altura visible = desde el borde superior del panel hasta el fondo de su contenedor.
    const container = sheet.parentElement?.getBoundingClientRect();
    const visible = (container?.bottom ?? window.innerHeight) - sheet.getBoundingClientRect().top;
    drag.current = { startY: event.clientY, startHeight: visible, height: visible, moved: false };
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const state = drag.current;
    if (!state) return;
    const dy = state.startY - event.clientY;
    if (Math.abs(dy) > 4) state.moved = true;
    if (!state.moved || !sheetRef.current) return;
    state.height = Math.max(0, state.startHeight + dy);
    sheetRef.current.dataset.dragging = "true";
    sheetRef.current.style.transform = `translateY(calc(var(--sheet-full) - ${Math.round(state.height)}px))`;
  }

  function onPointerUp() {
    const state = drag.current;
    drag.current = null;
    justDragged.current = Boolean(state?.moved);
    const sheet = sheetRef.current;
    if (sheet) {
      sheet.style.transform = ""; // vuelve a mandar el CSS de la altura anclada
      delete sheet.dataset.dragging;
    }
    if (!state?.moved) return;
    // Ancla a la altura más cercana (en fracciones del contenedor).
    const containerHeight = sheet?.parentElement?.clientHeight ?? window.innerHeight;
    const fraction = state.height / containerHeight;
    onSnapChange(fraction < 0.3 ? "peek" : fraction < 0.7 ? "half" : "full");
  }

  function onHandleKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      step(-1);
    }
  }

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const move = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!move && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const next =
      event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + move + tabs.length) % tabs.length;
    onTabChange(tabs[next].id);
    document.getElementById(`${id}-tab-${tabs[next].id}`)?.focus();
  }

  return (
    <div
      ref={sheetRef}
      className="sheet"
      data-snap={snap}
      role="region"
      aria-label={label}
    >
      <button
        type="button"
        className="sheet-handle"
        aria-label={`Ajustar el panel (ahora ${SNAP_LABELS[snap]})`}
        onClick={() => {
          if (justDragged.current) {
            justDragged.current = false;
            return;
          }
          onSnapChange(snap === "full" ? "peek" : SNAPS[SNAPS.indexOf(snap) + 1]);
        }}
        onKeyDown={onHandleKey}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span aria-hidden="true" />
      </button>
      <div className="sheet-tabs" role="tablist" aria-label={label}>
        {tabs.map((tab, index) => {
          const selected = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              id={`${id}-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${id}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => {
                onTabChange(tab.id);
                if (snap === "peek") onSnapChange("half");
              }}
              onKeyDown={(event) => onTabKey(event, index)}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${id}-panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`${id}-tab-${tab.id}`}
          className="sheet-panel"
          hidden={tab.id !== activeTab}
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
