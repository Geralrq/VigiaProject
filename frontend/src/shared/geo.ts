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
