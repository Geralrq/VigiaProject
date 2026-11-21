"use client";

import { useCallback, useState } from "react";

export interface GeoPosition {
  lat: number;
  lng: number;
  accuracyM: number;
}

type Status = "idle" | "loading" | "ok" | "denied" | "unavailable" | "timeout" | "unsupported";

const MESSAGES: Record<Exclude<Status, "idle" | "loading" | "ok">, string> = {
  denied: "No diste permiso para usar tu ubicación. Puedes escribir las coordenadas a mano.",
  unavailable: "No se pudo determinar tu ubicación. Puedes escribir las coordenadas a mano.",
  timeout: "La ubicación tardó demasiado. Inténtalo de nuevo o escribe las coordenadas a mano.",
  unsupported: "Tu navegador no ofrece ubicación. Escribe las coordenadas a mano.",
};

/** Ubicación actual con navigator.geolocation. Se pide solo al llamar a `request()`. */
export function useGeolocation() {
  const [status, setStatus] = useState<Status>("idle");
  const [position, setPosition] = useState<GeoPosition | null>(null);

  /** `onPosition` se llama con la posición cuando llega (p. ej. para guardarla enseguida). */
  const request = useCallback((onPosition?: (position: GeoPosition) => void) => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setStatus("unsupported");
      return;
    }
    setStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (result) => {
        const found = {
          lat: result.coords.latitude,
          lng: result.coords.longitude,
          accuracyM: result.coords.accuracy,
        };
        setPosition(found);
        setStatus("ok");
        onPosition?.(found);
      },
      (error) => {
        setStatus(
          error.code === error.PERMISSION_DENIED
            ? "denied"
            : error.code === error.TIMEOUT
              ? "timeout"
              : "unavailable",
        );
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  }, []);

  const failed = status === "denied" || status === "unavailable" || status === "timeout" || status === "unsupported";
  return {
    status,
    position,
    loading: status === "loading",
    /** true cuando conviene ofrecer el ingreso manual de coordenadas. */
    failed,
    message: failed ? MESSAGES[status] : null,
    request,
  };
}
