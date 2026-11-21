"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAlerts } from "@/features/alerts/api/queries";
import { useMe } from "@/features/auth/api/useMe";
import { useAnomalies, useHotspots, useZones } from "@/features/monitoring/api/queries";
import { NotificationToasts } from "@/features/notifications/components/NotificationToasts";
import { useReports } from "@/features/reports/api/queries";
import { geometryBbox, type Bbox } from "@/shared/geo";
import { BottomSheet, type SheetSnap } from "@/shared/ui/BottomSheet";
import { Icon } from "@/shared/ui/icons/Icon";
import { UiIcon } from "@/shared/ui/icons/ui";
import { useMediaQuery, withViewTransition } from "@/shared/ui/motion";
import { EmptyState, Skeleton } from "@/shared/ui/states";
import { toMapCollection, toPointCollection, zonesToCollection } from "../geojson";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { ANOMALY_TYPE_LABELS, anomalyIcon, formatNumber, percent } from "../labels";
import { fromAlert, fromAnomaly, type DetailModel, type Selection } from "../selection";
import { layersFromParams, selectionFromParams, toQueryString } from "../url-state";
import { AdminScan } from "./AdminScan";
import { DetailPanel } from "./DetailPanel";
import { EventList, type EventItem } from "./EventList";
import { ImpactCard } from "./ImpactCard";
import { LayerPanel, type LayerId, type LayerOption } from "./LayerPanel";
import { MapLegend } from "./MapLegend";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => (
    <div className="map-loading">
      <Skeleton label="Cargando mapa…" variant="block" />
    </div>
  ),
});

const BBOX_DEBOUNCE_MS = 400;
const MOBILE_QUERY = "(max-width: 52rem)"; // mismo corte que base.css

interface SelectionState extends Selection {
  /** Último dato conocido: el panel sigue mostrándose si el elemento sale del área cargada. */
  snapshot: { detail: DetailModel; geometry: GeoJSON.Geometry };
}

const intersects = (a: Bbox, b: Bbox) =>
  a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

export function CommandCenter() {
  const me = useMe();
  const role = me.data?.role;
  const isCitizen = role === "CIUDADANO";
  const isMobile = useMediaQuery(MOBILE_QUERY);

  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  // El estado inicial sale de la URL (enlace compartido); después la URL sigue al estado.
  const [active, setActive] = useState<Record<LayerId, boolean>>(() => layersFromParams(params));
  const [pendingFromUrl, setPendingFromUrl] = useState<Selection | null>(() => selectionFromParams(params));
  const [rawBbox, setRawBbox] = useState<Bbox | null>(null);
  const bbox = useDebouncedValue(rawBbox, BBOX_DEBOUNCE_MS);
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [focusBbox, setFocusBbox] = useState<Bbox | null>(null);
  const [sheetTab, setSheetTab] = useState("capas");
  const [sheetSnap, setSheetSnap] = useState<SheetSnap>("peek");

  const zones = useZones();
  const anomalies = useAnomalies(bbox);
  const hotspots = useHotspots(bbox, active.hotspots);
  const alertsEnabled = !isCitizen && role !== undefined;
  const alerts = useAlerts(alertsEnabled && active.alerts);
  const reports = useReports(bbox, active.reports);

  const layerOptions = useMemo<LayerOption[]>(
    () => [
      { id: "zones", label: "Zonas monitoreadas", icon: "geocerca" },
      { id: "anomalies", label: "Anomalías", icon: "marcador-anomalia" },
      { id: "hotspots", label: "Focos de calor (FIRMS)", icon: "foco" },
      ...(alertsEnabled
        ? [{ id: "alerts", label: "Alertas", icon: "marcador-alerta" } as const]
        : []),
      {
        id: "reports",
        label: isCitizen ? "Mis reportes" : "Reportes ciudadanos",
        icon: "marcador-reporte",
      },
    ],
    [alertsEnabled, isCitizen],
  );

  const zoneCollection = useMemo(() => zonesToCollection(zones.data ?? []), [zones.data]);
  const anomalyCollection = useMemo(
    () => toMapCollection(anomalies.data?.features ?? []),
    [anomalies.data],
  );
  const anomalyPoints = useMemo(
    () => toPointCollection(anomalies.data?.features ?? []),
    [anomalies.data],
  );
  const alertCollection = useMemo(
    () => toMapCollection(alerts.data?.features ?? []),
    [alerts.data],
  );
  const alertPoints = useMemo(
    () => toPointCollection(alerts.data?.features ?? []),
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
          icon: anomalyIcon(f.properties.type),
          label: `${ANOMALY_TYPE_LABELS[f.properties.type]} · ${zone} · ${percent(f.properties.confidence)}`,
        });
      }
    }
    if (alertsEnabled && active.alerts) {
      for (const f of visibleAlerts) {
        items.push({
          kind: "alert",
          id: f.id,
          icon: "geocerca",
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
      co2:
        known.length === 0
          ? null
          : known.reduce((s, f) => s + (f.properties.co2_tonnes ?? 0), 0),
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

  // Selección venida de la URL: se aplica (y el mapa vuela) cuando su dato ya está cargado.
  // Es estado derivado de props, así que se ajusta durante el render (patrón de React).
  if (pendingFromUrl) {
    const snapshot = resolve(pendingFromUrl);
    if (snapshot) {
      setPendingFromUrl(null);
      setSelection({ ...pendingFromUrl, snapshot });
      setFocusBbox(geometryBbox(snapshot.geometry));
      if (isMobile) {
        setSheetTab("detalle");
        setSheetSnap("half");
      }
    }
  }

  const select = useCallback(
    (target: Selection) => {
      const snapshot = resolve(target);
      if (!snapshot) return;
      withViewTransition(() => {
        setSelection({ ...target, snapshot });
        setFocusBbox(geometryBbox(snapshot.geometry));
        if (isMobile) {
          setSheetTab("detalle");
          setSheetSnap("half");
        }
      });
    },
    [resolve, isMobile],
  );

  const closeDetail = useCallback(() => {
    withViewTransition(() => {
      setSelection(null);
      if (isMobile) setSheetTab("capas");
    });
  }, [isMobile]);

  // La URL refleja capas y selección (replace: no llena el historial al mover cosas).
  const selectionKey = selection ? `${selection.kind}:${selection.id}` : null;
  useEffect(() => {
    const target = selectionKey
      ? ({ kind: selectionKey.split(":")[0], id: selectionKey.split(":")[1] } as Selection)
      : pendingFromUrl;
    const query = toQueryString(active, target);
    if (query === window.location.search.replace(/^\?/, "")) return;
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [active, selectionKey, pendingFromUrl, pathname, router]);

  const current = selection ? (resolve(selection) ?? selection.snapshot) : null;
  const firstError = [zones, anomalies, hotspots, alerts, reports].find((q) => q.isError)?.error;
  const loading = [anomalies, hotspots, alerts, reports].some((q) => q.isFetching);

  const controls = (
    <>
      <LayerPanel
        options={layerOptions}
        active={active}
        onToggle={(id) => setActive((prev) => ({ ...prev, [id]: !prev[id] }))}
      />
      <EventList items={events} selected={selection} onSelect={select} />
      {role === "ADMIN" && <AdminScan />}
    </>
  );
  const impact = (
    <ImpactCard
      title="Impacto en el área visible"
      hectares={visibleImpact.hectares}
      co2Tonnes={visibleImpact.co2}
    />
  );
  const detail =
    current && role ? (
      <DetailPanel
        key={`${current.detail.kind}-${selection?.id}`}
        detail={current.detail}
        role={role}
        onClose={closeDetail}
      />
    ) : null;

  const map = (
    <section className="map-area" aria-label="Mapa">
      <MapView
        active={active}
        zones={zoneCollection}
        anomalies={anomalyCollection}
        anomalyPoints={anomalyPoints}
        alerts={alertCollection}
        alertPoints={alertPoints}
        reports={reportCollection}
        hotspots={hotspots.data}
        selectedGeometry={current?.geometry ?? null}
        focusBbox={focusBbox}
        onBboxChange={setRawBbox}
        onSelect={select}
      />
      <p className="map-status" role={firstError ? "alert" : "status"}>
        {firstError
          ? `No se pudieron cargar algunos datos: ${firstError.message}`
          : loading
            ? "Actualizando datos…"
            : `${formatNumber(anomalies.data?.features.length ?? 0)} anomalías en el área`}
      </p>
      {!isMobile && <MapLegend />}
    </section>
  );

  if (isMobile) {
    return (
      <div className="command-center is-mobile" data-snap={sheetSnap}>
        <h1 className="visually-hidden">Centro de comando</h1>
        {map}
        <BottomSheet
          label="Paneles del mapa"
          activeTab={sheetTab}
          onTabChange={(tab) => withViewTransition(() => setSheetTab(tab))}
          snap={sheetSnap}
          onSnapChange={setSheetSnap}
          tabs={[
            {
              id: "capas",
              label: "Capas",
              icon: <UiIcon name="capas" size={18} />,
              content: (
                <div className="panel">
                  {controls}
                  <MapLegend open={false} />
                </div>
              ),
            },
            {
              id: "detalle",
              label: "Detalle",
              icon: <Icon name="marcador-anomalia" size={18} />,
              content: detail ?? (
                <div className="panel">
                  <EmptyState icon="marcador-anomalia" title="Nada seleccionado">
                    <p>Toca una anomalía o una alerta en el mapa, o elige una en Capas.</p>
                  </EmptyState>
                </div>
              ),
            },
            {
              id: "impacto",
              label: "Impacto",
              icon: <Icon name="satelite" size={18} />,
              content: <div className="panel">{impact}</div>,
            },
          ]}
        />
        <NotificationToasts />
      </div>
    );
  }

  return (
    <div className={`command-center${current ? " has-detail" : ""}`}>
      <h1 className="visually-hidden">Centro de comando</h1>
      <aside className="panel layers-panel" aria-labelledby="controls-title">
        <h2 id="controls-title" className="visually-hidden">
          Controles del mapa
        </h2>
        {controls}
        {impact}
      </aside>
      {map}
      {detail}
      <NotificationToasts />
    </div>
  );
}
