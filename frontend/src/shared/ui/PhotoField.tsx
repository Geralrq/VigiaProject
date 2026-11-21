"use client";

import { useId, type ChangeEvent } from "react";
import type { usePhotoPicker } from "@/shared/hooks/usePhotoPicker";
import { UiIcon } from "./icons/ui";

type Picker = ReturnType<typeof usePhotoPicker>;

interface Props {
  label: string;
  picker: Picker;
  hint?: string;
  /** Texto alternativo de la vista previa. */
  previewAlt: string;
}

/**
 * Foto desde la cámara del celular (o la galería en escritorio). La imagen se comprime en el
 * cliente (máx. 1600 px, JPEG) antes de enviarse; aquí solo se elige y se previsualiza.
 */
export function PhotoField({ label, picker, hint, previewAlt }: Props) {
  const id = useId();

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // permite volver a elegir la misma foto
    void picker.select(file);
  }

  return (
    <div className="form-field">
      <label htmlFor={id} className="label-with-icon">
        <UiIcon name="camara" size={18} /> {label}
      </label>
      <input
        id={id}
        type="file"
        accept="image/*"
        capture="environment"
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={onChange}
      />
      {hint && (
        <p id={`${id}-hint`} className="muted">
          {hint}
        </p>
      )}
      {picker.busy && <p role="status">Preparando la foto…</p>}
      {picker.error && (
        <p role="alert" className="error">
          {picker.error}
        </p>
      )}
      {picker.previewUrl && (
        <figure className="photo-preview">
          {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:) */}
          <img src={picker.previewUrl} alt={previewAlt} width={320} height={240} />
          <figcaption>
            <button type="button" onClick={picker.clear}>
              Quitar foto
            </button>
          </figcaption>
        </figure>
      )}
    </div>
  );
}
