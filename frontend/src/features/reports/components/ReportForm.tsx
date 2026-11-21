"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import type { ReportCategory, Urgency } from "@/shared/api/types";
import { useGeolocation } from "@/shared/hooks/useGeolocation";
import { usePhotoPicker } from "@/shared/hooks/usePhotoPicker";
import { ChoiceGroup, SelectField, TextAreaField, TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { PhotoField } from "@/shared/ui/PhotoField";
import { useCreateReport } from "../api/queries";
import { CATEGORY_LABELS, CATEGORY_ORDER, URGENCY_OPTIONS } from "../labels";

const MAX_DESCRIPTION = 2000;

type Errors = Partial<Record<"category" | "location" | "lat" | "lng" | "description", string>>;

function parseCoordinate(text: string, min: number, max: number): number | null {
  const value = Number(text.trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(value) && value >= min && value <= max ? value : null;
}

export function ReportForm() {
  const create = useCreateReport();
  const geo = useGeolocation();
  const photo = usePhotoPicker();
  const formRef = useRef<HTMLFormElement>(null);

  const [category, setCategory] = useState<ReportCategory | "">("");
  const [urgency, setUrgency] = useState<Urgency>("MEDIA");
  const [description, setDescription] = useState("");
  const [manualRequested, setManualRequested] = useState(false);
  const [manualLat, setManualLat] = useState("");
  const [manualLng, setManualLng] = useState("");
  const [errors, setErrors] = useState<Errors>({});

  const showManual = manualRequested || geo.failed;

  function reset() {
    create.reset();
    photo.clear();
    setCategory("");
    setUrgency("MEDIA");
    setDescription("");
    setManualRequested(false);
    setManualLat("");
    setManualLng("");
    setErrors({});
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found: Errors = {};
    if (!category) found.category = "Elige una categoría.";
    if (description.length > MAX_DESCRIPTION) {
      found.description = `La descripción admite como máximo ${MAX_DESCRIPTION} caracteres.`;
    }

    let point: { lat: number; lng: number } | null = null;
    if (showManual) {
      const lat = parseCoordinate(manualLat, -90, 90);
      const lng = parseCoordinate(manualLng, -180, 180);
      if (lat === null) found.lat = "Escribe una latitud entre -90 y 90, por ejemplo 4,65.";
      if (lng === null) found.lng = "Escribe una longitud entre -180 y 180, por ejemplo -74,08.";
      if (lat !== null && lng !== null) point = { lat, lng };
    } else if (geo.position) {
      point = geo.position;
    } else {
      found.location = "Indica dónde ocurre: usa tu ubicación o escribe las coordenadas.";
    }

    setErrors(found);
    if (Object.keys(found).length > 0 || !category || !point) {
      focusFirstInvalid(formRef.current);
      return;
    }
    create.mutate({ category, urgency, lat: point.lat, lng: point.lng, description, photo: photo.file });
  }

  if (create.isSuccess) {
    return (
      <div role="status">
        <h2>Reporte enviado</h2>
        <p>Gracias. Las autoridades lo revisarán y, si hace falta, verificarán el lugar.</p>
        <div className="actions">
          <button type="button" className="primary" onClick={reset}>
            Hacer otro reporte
          </button>
          <Link href="/mapa">Ir al centro de comando</Link>
        </div>
      </div>
    );
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Reportar un problema ambiental">
      <SelectField
        label="Categoría"
        name="category"
        value={category}
        error={errors.category}
        onChange={(e) => setCategory(e.target.value as ReportCategory | "")}
      >
        <option value="">Elige una categoría</option>
        {CATEGORY_ORDER.map((value) => (
          <option key={value} value={value}>
            {CATEGORY_LABELS[value]}
          </option>
        ))}
      </SelectField>

      <ChoiceGroup legend="Urgencia" name="urgency" value={urgency} options={URGENCY_OPTIONS} onChange={setUrgency} />

      <TextAreaField
        label="Descripción (opcional)"
        name="description"
        rows={4}
        value={description}
        error={errors.description}
        hint="Qué viste, desde cuándo y cómo llegar."
        onChange={(e) => setDescription(e.target.value)}
      />

      <PhotoField
        label="Foto (opcional)"
        picker={photo}
        previewAlt="Vista previa de la foto del reporte"
        hint="Se toma con la cámara y se reduce automáticamente antes de enviarse."
      />

      <fieldset className="location-field">
        <legend>Ubicación</legend>
        {geo.position && !showManual && (
          <p role="status">
            Ubicación tomada: <span className="mono">{geo.position.lat.toFixed(5)}, {geo.position.lng.toFixed(5)}</span>{" "}
            <span className="muted">(precisión ±{Math.round(geo.position.accuracyM)}&nbsp;m)</span>
          </p>
        )}
        {geo.message && (
          <p role="alert" className="error">
            {geo.message}
          </p>
        )}
        {errors.location && (
          <p role="alert" className="error">
            {errors.location}
          </p>
        )}
        <div className="actions">
          <button
            type="button"
            onClick={() => geo.request()}
            disabled={geo.loading}
            aria-busy={geo.loading}
            data-invalid={errors.location ? "true" : undefined}
          >
            {geo.loading ? "Buscando ubicación…" : geo.position ? "Actualizar mi ubicación" : "Usar mi ubicación"}
          </button>
          {!showManual && (
            <button type="button" onClick={() => setManualRequested(true)}>
              Escribir coordenadas
            </button>
          )}
        </div>
        {showManual && (
          <div className="field-row">
            <TextField
              label="Latitud"
              name="lat"
              inputMode="decimal"
              autoComplete="off"
              value={manualLat}
              error={errors.lat}
              onChange={(e) => setManualLat(e.target.value)}
            />
            <TextField
              label="Longitud"
              name="lng"
              inputMode="decimal"
              autoComplete="off"
              value={manualLng}
              error={errors.lng}
              onChange={(e) => setManualLng(e.target.value)}
            />
          </div>
        )}
      </fieldset>

      {create.isError && (
        <p role="alert" className="error">
          {create.error.message}
        </p>
      )}
      <button type="submit" className="primary" disabled={create.isPending || photo.busy} aria-busy={create.isPending}>
        {create.isPending ? "Enviando reporte…" : "Enviar reporte"}
      </button>
    </form>
  );
}
