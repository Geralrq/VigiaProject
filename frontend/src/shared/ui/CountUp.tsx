"use client";

import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./motion";

const DURATION_MS = 700;
const easeOut = (t: number) => 1 - (1 - t) ** 3;

/**
 * Cifra con conteo animado cuando aparece o cambia. El lector de pantalla recibe solo el valor
 * final (los intermedios son aria-hidden); con movimiento reducido salta directo al valor.
 */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    const start = from.current;
    if (prefersReducedMotion() || start === value) {
      from.current = value;
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    let frame = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / DURATION_MS);
      const current = start + (value - start) * easeOut(t);
      from.current = current;
      setShown(current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <>
      <span aria-hidden="true">{format(shown)}</span>
      <span className="visually-hidden">{format(value)}</span>
    </>
  );
}
