"use client";

import { useScanNow } from "@/features/monitoring/api/queries";
import { formatDate } from "../labels";
import { Icon } from "@/shared/ui/icons/Icon";

/** Solo se monta para ADMIN. El backend vuelve a exigir el rol. */
export function AdminScan() {
  const scan = useScanNow();
  const summary = scan.data;

  return (
    <section aria-label="Acciones de administrador">
      <h3>Administración</h3>
      <button
        type="button"
        className="primary"
        onClick={() => scan.mutate()}
        disabled={scan.isPending}
        aria-busy={scan.isPending}
      >
        <Icon name="satelite" size={18} />
        <span>{scan.isPending ? "Escaneando zonas…" : "Escanear ahora"}</span>
      </button>
      <div role="status">
        {summary && (
          <dl className="facts">
            <dt>Ventana</dt>
            <dd>
              {formatDate(summary.window_start)} – {formatDate(summary.window_end)}
            </dd>
            <dt>Zonas</dt>
            <dd>
              {summary.zones_scanned} escaneadas, {summary.zones_failed} con error
            </dd>
            <dt>Lecturas</dt>
            <dd>{summary.readings_saved}</dd>
            <dt>Focos</dt>
            <dd>{summary.hotspots_saved}</dd>
            <dt>Anomalías</dt>
            <dd>{summary.anomalies_detected} nuevas</dd>
          </dl>
        )}
      </div>
      {summary?.failures.map((failure) => (
        <p key={failure.zone_id} role="alert" className="error">
          {failure.zone_name}: {failure.error}
        </p>
      ))}
      {scan.isError && (
        <p role="alert" className="error">
          {scan.error.message}
        </p>
      )}
    </section>
  );
}
