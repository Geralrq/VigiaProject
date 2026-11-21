import type { LayerId } from "./components/LayerPanel";
import type { Selection } from "./selection";

/**
 * Estado compartible del centro de comando en la URL:
 *   /mapa?capas=zonas,anomalias,alertas&sel=anomalia:<uuid>
 * Las claves van en español (son visibles para quien comparte el enlace).
 */

const LAYER_SLUGS: Record<LayerId, string> = {
  zones: "zonas",
  anomalies: "anomalias",
  hotspots: "focos",
  alerts: "alertas",
  reports: "reportes",
};
const KIND_SLUGS: Record<Selection["kind"], string> = { anomaly: "anomalia", alert: "alerta" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const DEFAULT_LAYERS: Record<LayerId, boolean> = {
  zones: true,
  anomalies: true,
  hotspots: true,
  alerts: true,
  reports: false,
};

export function layersFromParams(params: URLSearchParams): Record<LayerId, boolean> {
  const raw = params.get("capas");
  if (raw === null) return DEFAULT_LAYERS;
  const wanted = new Set(raw.split(",").map((s) => s.trim()));
  const entries = (Object.keys(LAYER_SLUGS) as LayerId[]).map((id) => [id, wanted.has(LAYER_SLUGS[id])]);
  return Object.fromEntries(entries) as Record<LayerId, boolean>;
}

export function selectionFromParams(params: URLSearchParams): Selection | null {
  const [kindSlug, id] = (params.get("sel") ?? "").split(":");
  const kind = (Object.keys(KIND_SLUGS) as Selection["kind"][]).find((k) => KIND_SLUGS[k] === kindSlug);
  return kind && id && UUID.test(id) ? { kind, id } : null;
}

/** Query string del estado (vacía si todo está en sus valores por defecto). */
export function toQueryString(layers: Record<LayerId, boolean>, selection: Selection | null): string {
  const params = new URLSearchParams();
  const isDefault = (Object.keys(DEFAULT_LAYERS) as LayerId[]).every((id) => layers[id] === DEFAULT_LAYERS[id]);
  if (!isDefault) {
    const on = (Object.keys(LAYER_SLUGS) as LayerId[]).filter((id) => layers[id]).map((id) => LAYER_SLUGS[id]);
    params.set("capas", on.join(","));
  }
  if (selection) params.set("sel", `${KIND_SLUGS[selection.kind]}:${selection.id}`);
  return params.toString().replaceAll("%2C", ",").replaceAll("%3A", ":");
}
