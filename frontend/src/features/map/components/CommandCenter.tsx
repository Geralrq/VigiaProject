"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import { useAlerts } from "@/features/alerts/api/queries";
import { useMe } from "@/features/auth/api/useMe";
import { useAnomalies, useHotspots, useZones } from "@/features/monitoring/api/queries";
import { NotificationToasts } from "@/features/notifications/components/NotificationToasts";
import { useReports } from "@/features/reports/api/queries";
import { geometryBbox, type Bbox } from "@/shared/geo";
import { toMapCollection, zonesToCollection } from "../geojson";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { ANOMALY_TYPE_LABELS, formatNumber, percent } from "../labels";
import {
  fromAlert,
  fromAnomaly,
  type DetailModel,
  type Selection,
} from "../selection";
import { AdminScan } from "./AdminScan";
import { DetailPanel } from "./DetailPanel";
import { EventList, type EventItem } from "./EventList";
import { ImpactCard } from "./ImpactCard";
import { LayerPanel, type LayerId, type LayerOption } from "./LayerPanel";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => (
    <p role="status" className="map-status">
      Cargando mapa…
    </p>
  ),
});

const BBOX_DEBOUNCE_MS = 400;

interface SelectionState extends Selection {
  /** Último dato conocido: el panel sigue mostrándose si el elemento sale del área cargada. */
  snapshot: { detail: DetailModel; geometry: GeoJSON.Geometry };
}

const intersects = (a: Bbox, b: Bbox) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

export function CommandCenter() {
  const me = useMe();
  const role = me.data?.role;
  const isCitizen = role === "CIUDADANO";

  const [active, setActive] = useState<Record<LayerId, boolean>>({
    zones: true,
    anomalies: true,
    hotspots: true,
    alerts: true,
    reports: false,
  });
  const [rawBbox, setRawBbox] = useState<Bbox | null>(null);
  const bbox = useDebouncedValue(rawBbox, BBOX_DEBOUNCE_MS);
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [focusBbox, setFocusBbox] = useState<Bbox | null>(null);

  const zones = useZones();
  const anomalies = useAnomalies(bbox);
  const hotspots = useHotspots(bbox, active.hotspots);
  const alertsEnabled = !isCitizen && role !== undefined;
  const alerts = useAlerts(alertsEnabled && active.alerts);
  const reports = useReports(bbox, active.reports);

  const layerOptions = useMemo<LayerOption[]>(
    () => [
      { id: "zones", label: "Zonas monitoreadas" },
      { id: "anomalies", label: "Anomalías" },
      { id: "hotspots", label: "Focos de calor (FIRMS)" },
      ...(alertsEnabled ? [{ id: "alerts", label: "Alertas" } as const] : []),
      { id: "reports", label: isCitizen ? "Mis reportes" : "Reportes ciudadanos" },
    ],
    [alertsEnabled, isCitizen],
  );

  const zoneCollection = useMemo(() => zonesToCollection(zones.data ?? []), [zones.data]);
  const anomalyCollection = useMemo(
    () => toMapCollection(anomalies.data?.features ?? []),
    [anomalies.data],
  );
  const alertCollection = useMemo(
    () => toMapCollection(alerts.data?.features ?? []),
    [alerts.data],
  );
  const reportCollection = useMemo(
    () => toMapCollection(reports.data?.features ?? []),
    [reports.data],
  );

  const zoneNames = useMemo(
    () => new Map((zones.data ?? []).map((z) => [z.id, z.name])),
    [zones.data],
  );

  const visibleAlerts = useMemo(
    () =>
      (alerts.data?.features ?? []).filter((f) => {
        const box = geometryBbox(f.geometry);
        return !bbox || !box || intersects(box, bbox);
      }),
    [alerts.data, bbox],
  );

  const events = useMemo<EventItem[]>(() => {
    const items: EventItem[] = [];
    if (active.anomalies) {
      for (const f of anomalies.data?.features ?? []) {
        const zone = zoneNames.get(f.properties.zone_id) ?? "Zona";
        items.push({
          kind: "anomaly",
          id: f.id,
          label: `${ANOMALY_TYPE_LABELS[f.properties.type]} · ${zone} · ${percent(f.properties.confidence)}`,
        });
      }
    }
    if (alertsEnabled && active.alerts) {
      for (const f of visibleAlerts) {
        items.push({
          kind: "alert",
          id: f.id,
          label: `Alerta ${f.properties.risk_level.toLowerCase()} · ${f.properties.zone_name}`,
        });
      }
    }
    return items;
  }, [active.anomalies, active.alerts, alertsEnabled, anomalies.data, visibleAlerts, zoneNames]);

  const visibleImpact = useMemo(() => {
    const counted = (anomalies.data?.features ?? []).filter(
      (f) => f.properties.state !== "FALSO_POSITIVO",
    );
    const known = counted.filter((f) => f.properties.co2_tonnes !== null);
    return {
      hectares: counted.reduce((sum, f) => sum + f.properties.hectares, 0),
      co2: known.length === 0 ? null : known.reduce((s, f) => s + (f.properties.co2_tonnes ?? 0), 0),
    };
  }, [anomalies.data]);

  const resolve = useCallback(
    (target: Selection): SelectionState["snapshot"] | null => {
      if (target.kind === "anomaly") {
        const f = anomalies.data?.features.find((a) => a.id === target.id);
        return f
          ? {
              detail: fromAnomaly(f, zoneNames.get(f.properties.zone_id) ?? null),
              geometry: f.geometry as unknown as GeoJSON.Geometry,
            }
          : null;
      }
      const f = alerts.data?.features.find((a) => a.id === target.id);
      return f
        ? { detail: fromAlert(f), geometry: f.geometry as unknown as GeoJSON.Geometry }
        : null;
    },
    [anomalies.data, alerts.data, zoneNames],
  );

  const select = useCallback(
    (target: Selection, focus: boolean) => {
      const snapshot = resolve(target);
      if (!snapshot) return;
      setSelection({ ...target, snapshot });
      if (focus) setFocusBbox(geometryBbox(snapshot.geometry));
    },
    [resolve],
  );

  const current = selection ? (resolve(selection) ?? selection.snapshot) : null;
  const firstError = [zones, anomalies, hotspots, alerts, reports].find((q) => q.isError)?.error;
  const loading = [anomalies, hotspots, alerts, reports].some((q) => q.isFetching);

  return (
    <div className={`command-center${current ? " has-detail" : ""}`}>
      <h1 className="visually-hidden">Centro de comando</h1>
      <aside className="panel layers-panel" aria-labelledby="controls-title">
        <h2 id="controls-title" className="visually-hidden">
          Controles del mapa
        </h2>
        <LayerPanel
          options={layerOptions}
          active={active}
          onToggle={(id) => setActive((prev) => ({ ...prev, [id]: !prev[id] }))}
        />
        <ImpactCard
          title="Impacto en el área visible"
          hectares={visibleImpact.hectares}
          co2Tonnes={visibleImpact.co2}
        />
        <EventList
          items={events}
          selected={selection}
          onSelect={(target) => select(target, true)}
        />
        {role === "ADMIN" && <AdminScan />}
      </aside>

      <section className="map-area" aria-label="Mapa">
        <MapView
          active={active}
          zones={zoneCollection}
          anomalies={anomalyCollection}
          alerts={alertCollection}
          reports={reportCollection}
          hotspots={hotspots.data}
          selectedGeometry={current?.geometry ?? null}
          focusBbox={focusBbox}
          onBboxChange={setRawBbox}
          onSelect={(target) => select(target, false)}
        />
        <p className="map-status" role={firstError ? "alert" : "status"}>
          {firstError
            ? `No se pudieron cargar algunos datos: ${firstError.message}`
            : loading
              ? "Actualizando datos…"
              : `${formatNumber(anomalies.data?.features.length ?? 0)} anomalías en el área`}
        </p>
      </section>

      {current && role && (
        <DetailPanel
          key={`${current.detail.kind}-${selection?.id}`}
          detail={current.detail}
          role={role}
          onClose={() => setSelection(null)}
        />
      )}
      <NotificationToasts />
    </div>
  );
}
