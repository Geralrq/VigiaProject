import type {
  AlertFeature,
  AnomalyFeature,
  AnomalyState,
  AnomalyType,
  RiskLevel,
} from "@/shared/api/types";
import type { Bbox } from "@/shared/geo";

export type SelectionKind = "anomaly" | "alert";

export interface Selection {
  kind: SelectionKind;
  id: string;
}

/** Lo que el panel de detalle muestra, venga de una anomalía o de una alerta. */
export interface DetailModel {
  kind: SelectionKind;
  anomalyId: string;
  zoneId: string;
  zoneName: string | null;
  type: AnomalyType;
  state: AnomalyState | null;
  risk: RiskLevel | null;
  confidence: number;
  hectares: number;
  co2Tonnes: number | null;
  detectedAt: string;
  alertCreatedAt: string | null;
}

export function fromAnomaly(feature: AnomalyFeature, zoneName: string | null): DetailModel {
  const p = feature.properties;
  return {
    kind: "anomaly",
    anomalyId: feature.id,
    zoneId: p.zone_id,
    zoneName,
    type: p.type,
    state: p.state,
    risk: null,
    confidence: p.confidence,
    hectares: p.hectares,
    co2Tonnes: p.co2_tonnes,
    detectedAt: p.detected_at,
    alertCreatedAt: null,
  };
}

export function fromAlert(feature: AlertFeature): DetailModel {
  const p = feature.properties;
  return {
    kind: "alert",
    anomalyId: p.anomaly_id,
    zoneId: p.zone_id,
    zoneName: p.zone_name,
    type: p.anomaly_type as AnomalyType,
    state: null,
    risk: p.risk_level,
    confidence: p.confidence,
    hectares: p.hectares,
    co2Tonnes: p.co2_tonnes,
    detectedAt: p.detected_at,
    alertCreatedAt: p.created_at,
  };
}

/** Caja envolvente de una geometría GeoJSON (Polygon, MultiPolygon o Point). */
export function geometryBbox(geometry: object): Bbox | null {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  const visit = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") {
      minLon = Math.min(minLon, node[0]);
      maxLon = Math.max(maxLon, node[0]);
      minLat = Math.min(minLat, node[1]);
      maxLat = Math.max(maxLat, node[1]);
      return;
    }
    node.forEach(visit);
  };
  visit("coordinates" in geometry ? geometry.coordinates : null);
  return Number.isFinite(minLon) ? [minLon, minLat, maxLon, maxLat] : null;
}
