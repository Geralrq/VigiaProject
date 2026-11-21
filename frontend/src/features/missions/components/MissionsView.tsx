"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { ANOMALY_TYPE_LABELS, anomalyIcon, formatDate } from "@/features/map/labels";
import type { AnomalyType, MissionAnswerResult } from "@/shared/api/types";
import { useMissions } from "../api/queries";
import { MissionDetail } from "./MissionDetail";
import { EmptyState, ErrorState, Skeleton } from "@/shared/ui/states";
import { Icon } from "@/shared/ui/icons/Icon";

export function MissionsView() {
  const missions = useMissions();
  const selectedId = useSearchParams().get("m");
  const [results, setResults] = useState<Record<string, MissionAnswerResult>>({});

  if (missions.isPending) return <Skeleton label="Cargando tus misiones…" variant="list" lines={3} />;
  if (missions.isError) {
    return <ErrorState message={missions.error.message} onRetry={() => missions.refetch()} />;
  }

  const items = missions.data;
  const selected = items.find((m) => m.id === selectedId);
  const pending = items.filter((m) => m.state === "PENDIENTE").length;

  return (
    <div className="split" data-detail={selected ? "true" : "false"}>
      <section className="split-list" aria-label="Lista de misiones">
        {items.length > 0 && (
          <p className="muted">
            {pending} pendiente{pending === 1 ? "" : "s"} de {items.length}
          </p>
        )}
        {items.length === 0 ? (
          <EmptyState
            icon="mision"
            title="No tienes misiones"
            action={
              <Link className="button" href="/reportar">
                Reportar un problema
              </Link>
            }
          >
            <p>
              Cuando se detecte una anomalía cerca de ti, te avisaremos para que la verifiques.
              Guarda tu ubicación en tu perfil para recibirlas.
            </p>
          </EmptyState>
        ) : (
          <ul className="entry-list">
            {items.map((mission) => {
              const type = ANOMALY_TYPE_LABELS[mission.anomaly_type as AnomalyType] ?? mission.anomaly_type;
              return (
                <li key={mission.id}>
                  <Link
                    href={`/misiones?m=${mission.id}`}
                    aria-current={mission.id === selectedId ? "true" : undefined}
                  >
                    <span className="entry-title">
                      <Icon name={anomalyIcon(mission.anomaly_type)} size={18} />
                      {type} · {mission.zone_name}
                    </span>
                    <span className="muted">
                      {mission.state === "PENDIENTE" ? "Pendiente" : "Respondida"} ·{" "}
                      {formatDate(mission.created_at)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {selected ? (
        <section className="split-detail">
          <MissionDetail
            mission={selected}
            result={results[selected.id]}
            onAnswered={(result) => setResults((prev) => ({ ...prev, [selected.id]: result }))}
          />
        </section>
      ) : (
        selectedId && (
          <section className="split-detail" role="alert">
            <p>No encontramos esa misión. Elige una de la lista.</p>
          </section>
        )
      )}
    </div>
  );
}
