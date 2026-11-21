"use client";

import { useEffect, useId, useState } from "react";
import { ErrorState } from "@/shared/ui/states";
import { formatDate } from "../labels";

const IMAGE_SIZE = 768; // el backend entrega imágenes de hasta 768 px por lado
const HINT_KEY = "vigia.ba-hint-visto";

interface Props {
  beforeUrl: string | null;
  afterUrl: string | null;
  beforeDate: string;
  afterDate: string;
  loading: boolean;
  onRetry: () => void;
}

/** true si ya se mostró la pista (preferencia local; si el almacenamiento falla, se muestra). */
function hintAlreadySeen(): boolean {
  try {
    return window.localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function markHintSeen(): void {
  try {
    window.localStorage.setItem(HINT_KEY, "1");
  } catch {
    // Sin almacenamiento la pista vuelve a aparecer; no afecta al uso.
  }
}

/**
 * Comparador antes/después. El control real es un <input type="range"> nativo que cubre la
 * imagen (arrastre con dedo o ratón, flechas/Inicio/Fin con teclado, lector de pantalla); el
 * tirador visible solo lo acompaña y muestra hover, foco y arrastre.
 */
export function BeforeAfterSlider({
  beforeUrl,
  afterUrl,
  beforeDate,
  afterDate,
  loading,
  onRetry,
}: Props) {
  const rangeId = useId();
  const [position, setPosition] = useState(50);
  const [brokenUrls, setBrokenUrls] = useState<string[]>([]);
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    // Solo en el cliente (localStorage); la pista anima el tirador una vez.
    if (hintAlreadySeen()) return;
    const id = requestAnimationFrame(() => setShowHint(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const markBroken = (url: string) => setBrokenUrls((current) => [...current, url]);
  const usable = (url: string | null): url is string => url !== null && !brokenUrls.includes(url);

  function dismissHint() {
    if (!showHint) return;
    setShowHint(false);
    markHintSeen();
  }

  if (!usable(beforeUrl) || !usable(afterUrl)) {
    if (loading) {
      return (
        <div className="ba-frame ba-placeholder" role="status">
          <span className="visually-hidden">Preparando las imágenes satelitales…</span>
          <span className="skeleton-bar" aria-hidden="true" />
        </div>
      );
    }
    return (
      <ErrorState
        message="Las imágenes antes/después todavía no están disponibles."
        onRetry={() => {
          setBrokenUrls([]);
          onRetry();
        }}
      />
    );
  }

  return (
    <figure className="ba-slider">
      <div
        className="ba-frame"
        data-hint={showHint ? "true" : undefined}
        style={{ "--ba-position": `${position}%` } as React.CSSProperties}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
        <img
          src={beforeUrl}
          width={IMAGE_SIZE}
          height={IMAGE_SIZE}
          loading="lazy"
          decoding="async"
          alt={`Imagen satelital antes, ${formatDate(beforeDate)}`}
          onError={() => markBroken(beforeUrl)}
        />
        {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
        <img
          className="ba-after"
          src={afterUrl}
          width={IMAGE_SIZE}
          height={IMAGE_SIZE}
          loading="lazy"
          decoding="async"
          alt={`Imagen satelital después, ${formatDate(afterDate)}`}
          onError={() => markBroken(afterUrl)}
        />
        <span className="ba-divider" aria-hidden="true">
          <span className="ba-knob" />
        </span>
        {showHint && (
          <span className="ba-hint" aria-hidden="true">
            Desliza para comparar
          </span>
        )}
        <label htmlFor={rangeId} className="visually-hidden">
          Deslizar para comparar antes y después
        </label>
        <input
          id={rangeId}
          className="ba-range"
          type="range"
          min={0}
          max={100}
          step={1}
          value={position}
          aria-valuetext={`${position} % de la imagen posterior visible`}
          onChange={(event) => {
            setPosition(Number(event.target.value));
            dismissHint();
          }}
          onPointerDown={dismissHint}
        />
      </div>
      <figcaption className="ba-labels">
        {/* La imagen posterior se muestra a la izquierda del tirador. */}
        <span>Después · {formatDate(afterDate)}</span>
        <span>Antes · {formatDate(beforeDate)}</span>
      </figcaption>
    </figure>
  );
}
