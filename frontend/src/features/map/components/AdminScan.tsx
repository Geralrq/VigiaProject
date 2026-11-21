"use client";

import { useScanNow } from "@/features/monitoring/api/queries";
import { CountUp } from "@/shared/ui/CountUp";
import { Icon } from "@/shared/ui/icons/Icon";
import { ErrorState } from "@/shared/ui/states";
import { formatDate } from "../labels";
import { stagger } from "@/shared/ui/motion";

const integer = (n: number) => Math.round(n).toString();

/** Solo se monta para ADMIN. El backend vuelve a exigir el rol. */
export function AdminScan() {
  const scan = useScanNow();
  const summary = scan.data;

  return (
    <section aria-label="Acciones de administrador">
      <h3>Administración</h3>
      <button
        type="button"
        className="primary scan-button"
        onClick={() => scan.mutate()}
        disabled={scan.isPending}
        aria-busy={scan.isPending}
      >
        {scan.isPending ? (
          <span className="radar" aria-hidden="true" />
        ) : (
          <Icon name="satelite" size={18} />
        )}
        <span>{scan.isPending ? "Escaneando zonas…" : "Escanear ahora"}</span>
      </button>
      <div role="status">
        {summary && (
          <dl className="facts scan-summary stagger" key={summary.window_end + summary.readings_saved}>
            <dt style={stagger(0)}>Ventana</dt>
            <dd style={stagger(0)}>
              {formatDate(summary.window_start)} – {formatDate(summary.window_end)}
            </dd>
            <dt style={stagger(1)}>Zonas</dt>
            <dd style={stagger(1)}>
              <CountUp value={summary.zones_scanned} format={integer} /> escaneadas,{" "}
              {summary.zones_failed} con error
            </dd>
            <dt style={stagger(2)}>Lecturas</dt>
            <dd style={stagger(2)}>
              <CountUp value={summary.readings_saved} format={integer} />
            </dd>
            <dt style={stagger(3)}>Focos</dt>
            <dd style={stagger(3)}>
              <CountUp value={summary.hotspots_saved} format={integer} />
            </dd>
            <dt style={stagger(4)}>Anomalías</dt>
            <dd style={stagger(4)}>
              <CountUp value={summary.anomalies_detected} format={integer} /> nuevas
            </dd>
          </dl>
        )}
      </div>
      {summary?.failures.map((failure) => (
        <p key={failure.zone_id} role="alert" className="error">
          {failure.zone_name}: {failure.error}
        </p>
      ))}
      {scan.isError && <ErrorState message={scan.error.message} onRetry={() => scan.mutate()} />}
    </section>
  );
}
