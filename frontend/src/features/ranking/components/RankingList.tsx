"use client";

import { useMe } from "@/features/auth/api/useMe";
import { formatNumber } from "@/features/map/labels";
import { useLeaderboard } from "../api/queries";
import { EmptyState, ErrorState, Skeleton } from "@/shared/ui/states";

export function RankingList() {
  const ranking = useLeaderboard();
  const me = useMe();

  if (ranking.isPending) return <Skeleton label="Cargando el ranking…" variant="list" lines={5} />;
  if (ranking.isError) {
    return <ErrorState message={ranking.error.message} onRetry={() => ranking.refetch()} />;
  }

  return (
    <>
      {me.data && (
        <p>
          Tus puntos: <strong className="mono">{formatNumber(me.data.points)}</strong>
        </p>
      )}
      {ranking.data.length === 0 ? (
        <EmptyState icon="mision" title="Todavía nadie tiene puntos">
          <p>Responde una misión de verificación para abrir el ranking.</p>
        </EmptyState>
      ) : (
        <ol className="ranking">
          {ranking.data.map((entry, index) => (
            <li key={`${index}-${entry.name}`}>
              <span className="ranking-name">{entry.name}</span>
              <span className="mono">{formatNumber(entry.points)}&nbsp;pts</span>
            </li>
          ))}
        </ol>
      )}
      <p className="muted">
        Se puntúa cada misión respondida y cuando tu respuesta coincide con el resultado.
      </p>
    </>
  );
}
