"use client";

import { useId, useState } from "react";
import { formatDate } from "../labels";

interface Props {
  beforeUrl: string | null;
  afterUrl: string | null;
  beforeDate: string;
  afterDate: string;
  loading: boolean;
  onRetry: () => void;
}

/**
 * Comparador antes/después. El control es un <input type="range"> nativo: funciona con
 * teclado (flechas, Inicio, Fin) y lectores de pantalla. Valor = % visible de "después".
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

  const markBroken = (url: string) => setBrokenUrls((current) => [...current, url]);
  const usable = (url: string | null): url is string => url !== null && !brokenUrls.includes(url);

  if (!usable(beforeUrl) || !usable(afterUrl)) {
    return (
      <div role="status">
        <p>
          {loading
            ? "Preparando las imágenes satelitales…"
            : "Las imágenes antes/después todavía no están disponibles."}
        </p>
        <button
          type="button"
          onClick={() => {
            setBrokenUrls([]);
            onRetry();
          }}
          disabled={loading}
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <figure className="ba-slider">
      <div className="ba-frame">
        {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
        <img
          src={beforeUrl}
          alt={`Imagen satelital antes, ${formatDate(beforeDate)}`}
          onError={() => markBroken(beforeUrl)}
        />
        {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
        <img
          src={afterUrl}
          alt={`Imagen satelital después, ${formatDate(afterDate)}`}
          style={{ clipPath: `inset(0 0 0 ${100 - position}%)` }}
          onError={() => markBroken(afterUrl)}
        />
      </div>
      <label htmlFor={rangeId} className="visually-hidden">
        Deslizar para comparar antes y después
      </label>
      <input
        id={rangeId}
        className="ba-range"
        type="range"
        min={0}
        max={100}
        step={5}
        value={position}
        aria-valuetext={`${position} % de la imagen posterior visible`}
        onChange={(event) => setPosition(Number(event.target.value))}
      />
      <figcaption className="ba-labels">
        <span>Antes · {formatDate(beforeDate)}</span>
        <span>Después · {formatDate(afterDate)}</span>
      </figcaption>
    </figure>
  );
}
