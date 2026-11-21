/** [minLon, minLat, maxLon, maxLat] en WGS84. */
export type Bbox = [number, number, number, number];

/** Formato del parámetro `bbox` de la API; redondea para no recargar por movimientos mínimos. */
export function bboxParam(bbox: Bbox | null): string | undefined {
  return bbox ? bbox.map((n) => n.toFixed(2)).join(",") : undefined;
}

/** Fecha AAAA-MM-DD de hace `days` días (granularidad de un día: estable entre renders). */
export function daysAgoISO(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
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

/** Centro de la caja de una geometría como { lat, lng }, o null si no tiene coordenadas. */
export function geometryCenter(geometry: object): { lat: number; lng: number } | null {
  const box = geometryBbox(geometry);
  return box ? { lng: (box[0] + box[2]) / 2, lat: (box[1] + box[3]) / 2 } : null;
}

/** Enlace de Google Maps a un punto. */
export function googleMapsUrl(point: { lat: number; lng: number }): string {
  return `https://www.google.com/maps/search/?api=1&query=${point.lat},${point.lng}`;
}
