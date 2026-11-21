"use client";

import Link from "next/link";
import { useMe } from "@/features/auth/api/useMe";
import { RiskBadge } from "@/features/map/components/RiskBadge";
import { ANOMALY_TYPE_LABELS, anomalyIcon, formatDate, formatNumber } from "@/features/map/labels";
import type { AnomalyType, Inspection } from "@/shared/api/types";
import { INSPECTION_STATES, useInspections } from "../api/queries";
import { STATE_LABELS, asRiskLevel } from "../labels";
import { EmptyState, ErrorState, Skeleton } from "@/shared/ui/states";
import { Icon } from "@/shared/ui/icons/Icon";

function Entry({ inspection }: { inspection: Inspection }) {
  const risk = asRiskLevel(inspection.nivel_riesgo);
  const type = ANOMALY_TYPE_LABELS[inspection.tipo_anomalia as AnomalyType] ?? inspection.tipo_anomalia;
  return (
    <li>
      <Link href={`/inspecciones/${inspection.id}`}>
        <span className="entry-title">
          <Icon name={anomalyIcon(inspection.tipo_anomalia)} size={18} />
          {inspection.zona}
        </span>
        <span className="entry-meta">
          {risk && <RiskBadge level={risk} />}
          <span className="muted">
            {type} · {formatNumber(inspection.hectareas)}&nbsp;ha
          </span>
        </span>
        <span className="muted">
          {inspection.tecnico_nombre ? `Técnico: ${inspection.tecnico_nombre}` : "Sin técnico"} ·{" "}
          {formatDate(inspection.creada_en)}
        </span>
      </Link>
    </li>
  );
}

/** Tablero por estado. AUTORIDAD y ADMIN ven todos los tickets; el TÉCNICO solo los suyos. */
export function InspectionsBoard() {
  const inspections = useInspections();
  const me = useMe();

  if (inspections.isPending) return <Skeleton label="Cargando inspecciones…" variant="list" lines={4} />;
  if (inspections.isError) {
    return <ErrorState message={inspections.error.message} onRetry={() => inspections.refetch()} />;
  }

  const items = inspections.data;
  if (items.length === 0) {
    return (
      <EmptyState
        icon="informe"
        title={me.data?.role === "TECNICO" ? "No tienes inspecciones asignadas" : "Aún no hay inspecciones"}
      >
        <p>
          {me.data?.role === "TECNICO"
            ? "Cuando una autoridad te asigne un ticket, aparecerá aquí."
            : "Se crean solas cuando se emite una alerta. Mientras tanto, revisa el centro de comando."}
        </p>
      </EmptyState>
    );
  }

  return (
    <div className="board">
      {INSPECTION_STATES.map((state) => {
        const column = items.filter((i) => i.estado === state);
        return (
          <section key={state} aria-labelledby={`col-${state}`}>
            <h2 id={`col-${state}`}>
              {STATE_LABELS[state]} <span className="muted">({column.length})</span>
            </h2>
            {column.length === 0 ? (
              <p className="muted">Ninguna.</p>
            ) : (
              <ul className="entry-list">
                {column.map((inspection) => (
                  <Entry key={inspection.id} inspection={inspection} />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
