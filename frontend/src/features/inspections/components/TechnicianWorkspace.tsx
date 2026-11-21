"use client";

import { useRef, useState, type FormEvent } from "react";
import type { Inspection } from "@/shared/api/types";
import { usePhotoPicker } from "@/shared/hooks/usePhotoPicker";
import { TextAreaField, TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { PhotoField } from "@/shared/ui/PhotoField";
import {
  useCloseInspection,
  useSaveInspectionForm,
  useUploadInspectionPhoto,
} from "../api/queries";
import { FORM_FIELD_LABELS, parseMissingFields } from "../labels";

type FieldKey = "hallazgos" | "causa_probable" | "area_verificada_ha" | "fotos";

function parseArea(text: string): number | null | "invalid" {
  if (!text.trim()) return null;
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) && value >= 0 ? value : "invalid";
}

/**
 * Trabajo del técnico asignado: fotos de evidencia y formulario con borrador y cierre.
 * Al cerrar se guarda primero el borrador actual y luego se cierra; si el backend responde 422
 * se marcan los campos que faltan.
 */
export function TechnicianWorkspace({ inspection }: { inspection: Inspection }) {
  const upload = useUploadInspectionPhoto(inspection.id);
  const save = useSaveInspectionForm(inspection.id);
  const close = useCloseInspection(inspection.id);
  const picker = usePhotoPicker();
  const formRef = useRef<HTMLFormElement>(null);

  const form = inspection.formulario;
  const [hallazgos, setHallazgos] = useState(form?.hallazgos ?? "");
  const [causa, setCausa] = useState(form?.causa_probable ?? "");
  const [area, setArea] = useState(form?.area_verificada_ha?.toString().replace(".", ",") ?? "");
  const [selected, setSelected] = useState<string[]>(form?.fotos ?? []);
  const [missing, setMissing] = useState<FieldKey[]>([]);
  const [saved, setSaved] = useState(false);

  const busy = save.isPending || close.isPending;
  const error = (field: FieldKey) =>
    missing.includes(field) ? `Falta: ${FORM_FIELD_LABELS[field].toLowerCase()}.` : null;

  function payload() {
    const parsed = parseArea(area);
    return {
      hallazgos: hallazgos.trim() || null,
      causa_probable: causa.trim() || null,
      area_verificada_ha: parsed === "invalid" ? null : parsed,
      fotos: selected,
    };
  }

  function localMissing(): FieldKey[] {
    const found: FieldKey[] = [];
    if (!hallazgos.trim()) found.push("hallazgos");
    if (!causa.trim()) found.push("causa_probable");
    if (parseArea(area) === null || parseArea(area) === "invalid") found.push("area_verificada_ha");
    if (selected.length === 0) found.push("fotos");
    return found;
  }

  function onUpload() {
    if (!picker.file) return;
    upload.mutate(picker.file, {
      onSuccess: ({ path }) => {
        picker.clear();
        setSelected((current) => (current.includes(path) ? current : [...current, path]));
        setSaved(false);
      },
    });
  }

  function onSaveDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (parseArea(area) === "invalid") {
      setMissing(["area_verificada_ha"]);
      focusFirstInvalid(formRef.current);
      return;
    }
    setMissing([]);
    save.mutate(payload(), { onSuccess: () => setSaved(true) });
  }

  async function onClose() {
    const found = localMissing();
    setMissing(found);
    setSaved(false);
    if (found.length > 0) {
      focusFirstInvalid(formRef.current);
      return;
    }
    try {
      await save.mutateAsync(payload());
      await close.mutateAsync();
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "";
      const fromBackend = parseMissingFields(message).filter((f): f is FieldKey => f in FORM_FIELD_LABELS);
      if (fromBackend.length > 0) {
        setMissing(fromBackend);
        focusFirstInvalid(formRef.current);
      }
    }
  }

  const failure = close.error ?? save.error;
  const backendMissing = parseMissingFields(failure?.message ?? "");

  return (
    <>
      <section aria-labelledby="photos-title">
        <h2 id="photos-title">Fotos de evidencia</h2>
        {inspection.fotos.length === 0 ? (
          <p className="muted">Aún no hay fotos. Toma al menos una para poder cerrar.</p>
        ) : (
          <ul className="photo-grid">
            {inspection.fotos.map((photo, index) => (
              <li key={photo.path}>
                <label className="photo-choice">
                  {photo.url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- URL firmada externa
                    <img src={photo.url} alt={`Foto ${index + 1} del ticket`} width={160} height={120} loading="lazy" />
                  ) : (
                    <span className="muted">Foto {index + 1} (no disponible)</span>
                  )}
                  <span>
                    <input
                      type="checkbox"
                      checked={selected.includes(photo.path)}
                      onChange={(e) => {
                        setSelected((current) =>
                          e.target.checked
                            ? [...current, photo.path]
                            : current.filter((p) => p !== photo.path),
                        );
                        setSaved(false);
                      }}
                    />{" "}
                    Incluir en el informe
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <PhotoField
          label="Agregar foto"
          picker={picker}
          previewAlt="Vista previa de la foto de evidencia"
          hint="Se reduce automáticamente antes de subirla."
        />
        {upload.isError && (
          <p role="alert" className="error">
            {upload.error.message}
          </p>
        )}
        <button
          type="button"
          onClick={onUpload}
          disabled={!picker.file || upload.isPending}
          aria-busy={upload.isPending}
        >
          {upload.isPending ? "Subiendo foto…" : "Subir foto"}
        </button>
      </section>

      <section aria-labelledby="form-title">
        <h2 id="form-title">Formulario de inspección</h2>
        <form ref={formRef} onSubmit={onSaveDraft} noValidate aria-label="Formulario de inspección">
          <TextAreaField
            label="Hallazgos"
            name="hallazgos"
            rows={5}
            value={hallazgos}
            error={error("hallazgos")}
            onChange={(e) => {
              setHallazgos(e.target.value);
              setSaved(false);
            }}
          />
          <TextAreaField
            label="Causa probable"
            name="causa_probable"
            rows={3}
            value={causa}
            error={error("causa_probable")}
            onChange={(e) => {
              setCausa(e.target.value);
              setSaved(false);
            }}
          />
          <TextField
            label="Área verificada (hectáreas)"
            name="area_verificada_ha"
            inputMode="decimal"
            autoComplete="off"
            value={area}
            error={
              parseArea(area) === "invalid" && missing.includes("area_verificada_ha")
                ? "Escribe un número, por ejemplo 12,5."
                : error("area_verificada_ha")
            }
            onChange={(e) => {
              setArea(e.target.value);
              setSaved(false);
            }}
          />
          {missing.includes("fotos") && (
            <p role="alert" data-invalid="true" tabIndex={-1} className="error">
              Falta: {FORM_FIELD_LABELS.fotos.toLowerCase()}. Sube una foto y márcala para incluirla.
            </p>
          )}
          {backendMissing.length > 0 && (
            <p role="alert" className="error">
              Para cerrar falta: {backendMissing.map((f) => FORM_FIELD_LABELS[f] ?? f).join(", ")}.
            </p>
          )}
          {failure && backendMissing.length === 0 && (
            <p role="alert" className="error">
              {failure.message}
            </p>
          )}
          {saved && <p role="status">Borrador guardado.</p>}
          <div className="actions">
            <button type="submit" disabled={busy} aria-busy={save.isPending && !close.isPending}>
              {save.isPending && !close.isPending ? "Guardando…" : "Guardar borrador"}
            </button>
            <button type="button" className="primary" onClick={onClose} disabled={busy} aria-busy={close.isPending}>
              {close.isPending ? "Cerrando…" : "Cerrar inspección"}
            </button>
          </div>
          <p className="muted">
            Al cerrar se genera el informe PDF y el ticket ya no se puede editar.
          </p>
        </form>
      </section>
    </>
  );
}
