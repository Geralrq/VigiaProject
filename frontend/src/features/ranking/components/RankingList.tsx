"use client";

import { useMe } from "@/features/auth/api/useMe";
import { formatNumber } from "@/features/map/labels";
import { useLeaderboard } from "../api/queries";

export function RankingList() {
  const ranking = useLeaderboard();
  const me = useMe();

  if (ranking.isPending) return <p role="status">Cargando el ranking…</p>;
  if (ranking.isError) {
    return (
      <div role="alert">
        <p className="error">{ranking.error.message}</p>
        <button type="button" onClick={() => ranking.refetch()}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <>
      {me.data && (
        <p>
          Tus puntos: <strong className="mono">{formatNumber(me.data.points)}</strong>
        </p>
      )}
      {ranking.data.length === 0 ? (
        <p>Todavía nadie tiene puntos. Responde una misión para abrir el ranking.</p>
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
