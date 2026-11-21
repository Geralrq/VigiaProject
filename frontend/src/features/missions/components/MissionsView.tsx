"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { ANOMALY_TYPE_LABELS, formatDate } from "@/features/map/labels";
import type { AnomalyType, MissionAnswerResult } from "@/shared/api/types";
import { useMissions } from "../api/queries";
import { MissionDetail } from "./MissionDetail";

export function MissionsView() {
  const missions = useMissions();
  const selectedId = useSearchParams().get("m");
  const [results, setResults] = useState<Record<string, MissionAnswerResult>>({});

  if (missions.isPending) return <p role="status">Cargando tus misiones…</p>;
  if (missions.isError) {
    return (
      <div role="alert">
        <p className="error">{missions.error.message}</p>
        <button type="button" onClick={() => missions.refetch()}>
          Reintentar
        </button>
      </div>
    );
  }

  const items = missions.data;
  const selected = items.find((m) => m.id === selectedId);
  const pending = items.filter((m) => m.state === "PENDIENTE").length;

  return (
    <div className="split" data-detail={selected ? "true" : "false"}>
      <section className="split-list" aria-label="Lista de misiones">
        <p className="muted">
          {items.length === 0
            ? "Todavía no tienes misiones."
            : `${pending} pendiente${pending === 1 ? "" : "s"} de ${items.length}`}
        </p>
        {items.length === 0 ? (
          <p>
            Cuando se detecte una anomalía cerca de ti, te avisaremos para que la verifiques.
            Mientras tanto puedes <Link href="/reportar">reportar un problema</Link>.
          </p>
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
