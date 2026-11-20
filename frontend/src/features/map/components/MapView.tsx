"use client";

import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type IControl,
  type MapGeoJSONFeature,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { HotspotCollection } from "@/shared/api/types";
import type { Bbox } from "@/shared/geo";
import { readNumberToken, readRgbToken, readToken } from "@/shared/styles/tokens";
import { EMPTY_COLLECTION } from "../geojson";
import type { Selection } from "../selection";
import type { LayerId } from "./LayerPanel";

// Mapa base gratuito y sin token: teselas raster de OpenStreetMap, invertidas a oscuro con los
// tokens --map-base-* (se lee en el cliente, cuando ya existe el documento).
function baseStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "© colaboradores de OpenStreetMap",
      },
    },
    layers: [
      {
        id: "osm",
        type: "raster",
        source: "osm",
        paint: {
          "raster-brightness-min": readNumberToken("--map-base-brightness-min"),
          "raster-brightness-max": readNumberToken("--map-base-brightness-max"),
          "raster-saturation": readNumberToken("--map-base-saturation"),
          "raster-contrast": readNumberToken("--map-base-contrast"),
          "raster-hue-rotate": readNumberToken("--map-base-hue-rotate"),
        },
      },
    ],
  };
}

const RISK_LEVELS = ["BAJO", "MEDIO", "ALTO", "CRITICO"] as const;

// El worker se sirve como estático (ver scripts/sync-maplibre-worker.mjs); el que MapLibre
// resuelve solo no carga empaquetado con Turbopack.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const COLOMBIA_CENTER: [number, number] = [-74.3, 4.6];
const COLOMBIA_ZOOM = 5;

// Capas de MapLibre que se encienden/apagan por cada capa del panel.
const LAYER_IDS: Record<Exclude<LayerId, "hotspots">, string[]> = {
  zones: ["zones-fill", "zones-line"],
  anomalies: ["anomalies-fill", "anomalies-line"],
  alerts: ["alerts-fill", "alerts-line"],
  reports: ["reports-circle"],
};

const CLICKABLE: { layerId: string; kind: Selection["kind"] }[] = [
  { layerId: "anomalies-fill", kind: "anomaly" },
  { layerId: "alerts-fill", kind: "alert" },
];

interface Props {
  active: Record<LayerId, boolean>;
  zones: GeoJSON.FeatureCollection;
  anomalies: GeoJSON.FeatureCollection;
  alerts: GeoJSON.FeatureCollection;
  reports: GeoJSON.FeatureCollection;
  hotspots: HotspotCollection | undefined;
  selectedGeometry: GeoJSON.Geometry | null;
  focusBbox: Bbox | null;
  onBboxChange: (bbox: Bbox) => void;
  onSelect: (selection: Selection) => void;
}

function setSourceData(map: MapLibreMap, id: string, data: GeoJSON.GeoJSON): void {
  (map.getSource(id) as GeoJSONSource | undefined)?.setData(data);
}

export default function MapView(props: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [ready, setReady] = useState(false);

  // Los manejadores de eventos del mapa siempre llaman a la última versión de los callbacks.
  const callbacks = useRef({ onBboxChange: props.onBboxChange, onSelect: props.onSelect });
  useEffect(() => {
    callbacks.current = { onBboxChange: props.onBboxChange, onSelect: props.onSelect };
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new MapLibreMap({
      container,
      style: baseStyle(),
      center: COLOMBIA_CENTER,
      zoom: COLOMBIA_ZOOM,
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl(), "bottom-right");

    const reportBounds = () => {
      const [[west, south], [east, north]] = map.getBounds().toArray();
      callbacks.current.onBboxChange([west, south, east, north]);
    };

    map.on("load", () => {
      const zoneFill = readToken("--map-zone-fill");
      const zoneLine = readToken("--map-zone-line");
      const fire = readToken("--map-anomaly-fire");
      const deforestation = readToken("--map-anomaly-deforestation");
      const typeColor = ["match", ["get", "type"], "INCENDIO", fire, deforestation] as const;
      // Alertas: el color es el nivel de riesgo (el glifo y el texto viven en el panel).
      const riskColor = [
        "match",
        ["get", "risk_level"],
        ...RISK_LEVELS.flatMap((level) => [level, readToken(`--risk-${level.toLowerCase()}`)]),
        readToken("--color-text-muted"),
      ];
      const confidenceOpacity = ["interpolate", ["linear"], ["get", "confidence"], 0, 0.25, 1, 0.7];

      for (const id of ["zones", "alerts", "anomalies", "reports", "selection"]) {
        map.addSource(id, { type: "geojson", data: EMPTY_COLLECTION });
      }
      map.addLayer({
        id: "zones-fill",
        type: "fill",
        source: "zones",
        paint: { "fill-color": zoneFill, "fill-opacity": 0.07 },
      });
      map.addLayer({
        id: "zones-line",
        type: "line",
        source: "zones",
        paint: { "line-color": zoneLine, "line-width": 1.25 },
      });
      map.addLayer({
        id: "alerts-fill",
        type: "fill",
        source: "alerts",
        paint: { "fill-color": riskColor as never, "fill-opacity": 0.08 },
      });
      map.addLayer({
        id: "alerts-line",
        type: "line",
        source: "alerts",
        paint: {
          "line-color": riskColor as never,
          "line-width": 2,
          "line-dasharray": [3, 2],
        },
      });
      map.addLayer({
        id: "anomalies-fill",
        type: "fill",
        source: "anomalies",
        paint: { "fill-color": typeColor as never, "fill-opacity": confidenceOpacity as never },
      });
      map.addLayer({
        id: "anomalies-line",
        type: "line",
        source: "anomalies",
        paint: { "line-color": typeColor as never, "line-width": 2 },
      });
      map.addLayer({
        id: "reports-circle",
        type: "circle",
        source: "reports",
        paint: {
          "circle-radius": 6,
          "circle-color": readToken("--map-report"),
          "circle-stroke-color": readToken("--color-bg"),
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "selection-line",
        type: "line",
        source: "selection",
        paint: { "line-color": readToken("--map-selection"), "line-width": 4 },
      });

      const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlay as unknown as IControl);
      overlayRef.current = overlay;

      reportBounds();
      setReady(true);
    });

    map.on("moveend", reportBounds);
    map.on("click", (event) => {
      for (const { layerId, kind } of CLICKABLE) {
        if (!map.getLayer(layerId)) continue;
        const hit = map.queryRenderedFeatures(event.point, { layers: [layerId] })[0] as
          | MapGeoJSONFeature
          | undefined;
        const id = hit?.properties?.featureId;
        if (typeof id === "string") {
          callbacks.current.onSelect({ kind, id });
          return;
        }
      }
    });

    return () => {
      setReady(false);
      overlayRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, []);

  const { zones, anomalies, alerts, reports, hotspots, active, selectedGeometry, focusBbox } = props;

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setSourceData(map, "zones", zones);
    setSourceData(map, "anomalies", anomalies);
    setSourceData(map, "alerts", alerts);
    setSourceData(map, "reports", reports);
  }, [ready, zones, anomalies, alerts, reports]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const [layer, ids] of Object.entries(LAYER_IDS)) {
      const visibility = active[layer as keyof typeof LAYER_IDS] ? "visible" : "none";
      ids.forEach((id) => map.setLayoutProperty(id, "visibility", visibility));
    }
  }, [ready, active]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setSourceData(
      map,
      "selection",
      selectedGeometry
        ? { type: "Feature", geometry: selectedGeometry, properties: {} }
        : EMPTY_COLLECTION,
    );
  }, [ready, selectedGeometry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !focusBbox) return;
    const [west, south, east, north] = focusBbox;
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 48, maxZoom: 12 },
    );
  }, [ready, focusBbox]);

  // Focos de calor FIRMS: heatmap de deck.gl montado sobre MapLibre.
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!ready || !overlay) return;
    // Ámbar → rojo, con opacidad creciente con la densidad de focos.
    const from = readRgbToken("--map-hotspot-from-rgb");
    const to = readRgbToken("--map-hotspot-to-rgb");
    const stops = [0, 0.2, 0.4, 0.6, 0.8, 1];
    const colorRange = stops.map((t, i) => [
      ...from.map((c, k) => Math.round(c + (to[k] - c) * t)),
      [30, 80, 130, 180, 220, 255][i],
    ]) as [number, number, number, number][];
    overlay.setProps({
      layers: active.hotspots
        ? [
            new HeatmapLayer({
              id: "hotspots-heat",
              data: hotspots?.features ?? [],
              getPosition: (f: NonNullable<typeof hotspots>["features"][number]) =>
                f.geometry.coordinates,
              getWeight: (f: NonNullable<typeof hotspots>["features"][number]) =>
                f.properties.frp ?? 1,
              radiusPixels: 40,
              intensity: 2,
              colorRange,
            }),
          ]
        : [],
    });
  }, [ready, active.hotspots, hotspots]);

  return (
    <div
      ref={containerRef}
      className="map-canvas"
      role="region"
      aria-label="Mapa interactivo de Colombia"
    />
  );
}
