"use client";

import { useSyncExternalStore, type CSSProperties } from "react";

const MAX_STAGGER = 12;

/** Índice para la aparición escalonada de listas (CSS: animation-delay = --i × paso). */
export function stagger(index: number): CSSProperties {
  return { "--i": Math.min(index, MAX_STAGGER) } as CSSProperties;
}
import { flushSync } from "react-dom";

const REDUCED = "(prefers-reduced-motion: reduce)";

// Una función de suscripción estable por query: si cambiara en cada render,
// useSyncExternalStore se volvería a suscribir cada vez.
const subscribers = new Map<string, (onChange: () => void) => () => void>();

function subscribeMedia(query: string) {
  let subscribe = subscribers.get(query);
  if (!subscribe) {
    subscribe = (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    };
    subscribers.set(query, subscribe);
  }
  return subscribe;
}

/** Coincidencia de una media query, reactiva. En el servidor siempre es false. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    subscribeMedia(query),
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia(REDUCED).matches;
}

export function useReducedMotion(): boolean {
  return useMediaQuery(REDUCED);
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => unknown;
};

/**
 * Aplica un cambio de estado dentro de una View Transition si el navegador la soporta y el
 * usuario no pidió menos movimiento; si no, lo aplica directamente.
 */
export function withViewTransition(update: () => void): void {
  const doc = typeof document === "undefined" ? null : (document as ViewTransitionDocument);
  if (!doc?.startViewTransition || prefersReducedMotion()) {
    update();
    return;
  }
  doc.startViewTransition(() => flushSync(update));
}
