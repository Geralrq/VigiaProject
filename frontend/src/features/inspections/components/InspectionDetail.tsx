"use client";

import Link from "next/link";
import { useMe } from "@/features/auth/api/useMe";
import { RiskBadge } from "@/features/map/components/RiskBadge";
import { ANOMALY_TYPE_LABELS, formatDate, formatNumber } from "@/features/map/labels";
import type { AnomalyType, Inspection, Profile } from "@/shared/api/types";
import { useInspection } from "../api/queries";
import { FORM_FIELD_LABELS, STATE_LABELS, asRiskLevel } from "../labels";
import { AssignSection } from "./AssignSection";
import { PdfButton } from "./PdfButton";
import { TechnicianWorkspace } from "./TechnicianWorkspace";

function ReadOnlyForm({ inspection }: { inspection: Inspection }) {
  const form = inspection.formulario;
  if (!form) return <p className="muted">El técnico todavía no llenó el formulario.</p>;
  return (
    <dl className="facts">
      <dt>{FORM_FIELD_LABELS.hallazgos}</dt>
      <dd>{form.hallazgos ?? "—"}</dd>
      <dt>{FORM_FIELD_LABELS.causa_probable}</dt>
      <dd>{form.causa_probable ?? "—"}</dd>
      <dt>{FORM_FIELD_LABELS.area_verificada_ha}</dt>
      <dd>{form.area_verificada_ha === null ? "—" : formatNumber(form.area_verificada_ha)}</dd>
    </dl>
  );
}

function Photos({ inspection }: { inspection: Inspection }) {
  if (inspection.fotos.length === 0) return <p className="muted">Sin fotos de evidencia.</p>;
  return (
    <ul className="photo-grid">
      {inspection.fotos.map((photo, index) => (
        <li key={photo.path}>
          {photo.url ? (
            // eslint-disable-next-line @next/next/no-img-element -- URL firmada externa
            <img src={photo.url} alt={`Foto ${index + 1} de evidencia`} width={160} height={120} loading="lazy" />
          ) : (
            <span className="muted">Foto {index + 1} (no disponible)</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function InspectionDetail({ id }: { id: string }) {
  const inspection = useInspection(id);
  const me = useMe();

  if (inspection.isPending || me.isPending) return <p role="status">Cargando inspección…</p>;
  if (inspection.isError || me.isError) {
    const message = inspection.error?.message ?? me.error?.message ?? "No se pudo cargar.";
    return (
      <div role="alert">
        <p className="error">{message}</p>
        <button type="button" onClick={() => inspection.refetch()}>
          Reintentar
        </button>
        <p>
          <Link href="/inspecciones">Volver al tablero</Link>
        </p>
      </div>
    );
  }

  const data = inspection.data;
  const profile: Profile = me.data;
  const isStaff = profile.role === "AUTORIDAD" || profile.role === "ADMIN";
  const isAssignedTechnician = profile.role === "TECNICO" && data.tecnico_id === profile.id;
  const canEdit = isAssignedTechnician && (data.estado === "ASIGNADO" || data.estado === "EN_PROGRESO");
  const canAssign = isStaff && (data.estado === "ABIERTO" || data.estado === "ASIGNADO");
  const risk = asRiskLevel(data.nivel_riesgo);
  const type = ANOMALY_TYPE_LABELS[data.tipo_anomalia as AnomalyType] ?? data.tipo_anomalia;

  return (
    <article aria-labelledby="inspection-title">
      <p>
        <Link href="/inspecciones" className="back-link">
          Volver al tablero
        </Link>
      </p>
      <h1 id="inspection-title">{data.zona}</h1>
      <dl className="facts">
        <dt>Estado</dt>
        <dd>{STATE_LABELS[data.estado]}</dd>
        {risk && (
          <>
            <dt>Riesgo</dt>
            <dd>
              <RiskBadge level={risk} />
            </dd>
          </>
        )}
        <dt>Anomalía</dt>
        <dd>{type}</dd>
        <dt>Superficie</dt>
        <dd>{formatNumber(data.hectareas)}&nbsp;hectáreas</dd>
        <dt>Carbono</dt>
        <dd>
          {data.co2_estimado_t === null ? "sin dato" : `${formatNumber(data.co2_estimado_t)} t de CO₂`}{" "}
          <span className="muted">(estimación)</span>
        </dd>
        <dt>Detectada</dt>
        <dd>
          <time dateTime={data.detectada_en}>{formatDate(data.detectada_en)}</time>
        </dd>
        <dt>Ticket creado</dt>
        <dd>
          <time dateTime={data.creada_en}>{formatDate(data.creada_en)}</time>
        </dd>
        <dt>Técnico</dt>
        <dd>{data.tecnico_nombre ?? "Sin asignar"}</dd>
        {data.cerrada_en && (
          <>
            <dt>Cerrado</dt>
            <dd>
              <time dateTime={data.cerrada_en}>{formatDate(data.cerrada_en)}</time>
            </dd>
          </>
        )}
      </dl>

      <div className="actions">
        <a className="button" href={data.ruta_google_maps} target="_blank" rel="noopener noreferrer">
          Abrir ruta en Google Maps
        </a>
        {(isStaff || isAssignedTechnician) && <PdfButton inspectionId={data.id} />}
      </div>

      {canAssign && <AssignSection key={data.tecnico_id ?? "sin-tecnico"} inspection={data} />}

      {canEdit ? (
        <TechnicianWorkspace key={data.id} inspection={data} />
      ) : (
        <>
          <section aria-labelledby="photos-title">
            <h2 id="photos-title">Fotos de evidencia</h2>
            <Photos inspection={data} />
          </section>
          <section aria-labelledby="form-title">
            <h2 id="form-title">Formulario de inspección</h2>
            <ReadOnlyForm inspection={data} />
          </section>
        </>
      )}
    </article>
  );
}
