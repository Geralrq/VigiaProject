"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { compressImage, ImageError } from "@/shared/images/compress";

interface PhotoState {
  /** Foto ya comprimida, lista para enviar. */
  file: File | null;
  previewUrl: string | null;
  busy: boolean;
  error: string | null;
}

const EMPTY: PhotoState = { file: null, previewUrl: null, busy: false, error: null };

/** Elegir/tomar una foto, comprimirla en el cliente y mostrar su vista previa. */
export function usePhotoPicker() {
  const [state, setState] = useState<PhotoState>(EMPTY);
  const attempt = useRef(0); // descarta resultados de elecciones anteriores si se elige otra rápido

  const previewUrl = state.previewUrl;
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const select = useCallback(async (picked: File | null | undefined) => {
    const current = ++attempt.current;
    if (!picked) {
      setState(EMPTY);
      return;
    }
    setState({ ...EMPTY, busy: true });
    try {
      const file = await compressImage(picked);
      if (current === attempt.current) {
        setState({ file, previewUrl: URL.createObjectURL(file), busy: false, error: null });
      }
    } catch (error) {
      if (current === attempt.current) {
        const message =
          error instanceof ImageError ? error.message : "No se pudo preparar la foto. Inténtalo de nuevo.";
        setState({ ...EMPTY, error: message });
      }
    }
  }, []);

  const clear = useCallback(() => {
    attempt.current++;
    setState(EMPTY);
  }, []);

  return { ...state, select, clear };
}
