/**
 * Iconos propios de Vigía: trazo fino (1,5 en una cuadrícula de 24), puntas redondas, sin
 * relleno salvo los puntos. Es la única fuente de los dibujos: <Icon> los pinta en React y
 * markerSvg() los convierte en marcadores para MapLibre.
 */

export type Shape =
  | { d: string; fill?: boolean; dash?: string }
  | { cx: number; cy: number; r: number; fill?: boolean };

export const ICONS = {
  incendio: [
    { d: "M12 3c.8 3.2 5 5.4 5 10a5 5 0 0 1-10 0c0-2.2 1-3.8 2.2-5 .3 1.7 1.1 2.7 2.3 3.2C11.2 8.5 11.4 5.6 12 3Z" },
    { d: "M12 20a2 2 0 0 1-2-2c0-1.3.9-2.1 2-3.2 1.1 1.1 2 1.9 2 3.2a2 2 0 0 1-2 2Z" },
  ],
  deforestacion: [
    { d: "M8 3 4 10h2.6L4 14h8l-2.6-4H12L8 3Z" },
    { d: "M8 14v4" },
    { d: "M15 14.5h4V18h-4Z" },
    { cx: 17, cy: 14.5, r: 0.9, fill: true },
    { d: "M3 18.5h18" },
  ],
  inundacion: [
    { d: "M5.5 11 12 5.5l6.5 5.5" },
    { d: "M7.5 9.5V14M16.5 9.5V14" },
    { d: "M3 17c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1 1.5 1 3 1" },
    { d: "M3 20.5c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1 1.5 1 3 1" },
  ],
  satelite: [
    { d: "M12 8.2 15.8 12 12 15.8 8.2 12Z" },
    { d: "M9.6 9.6 6 6M14.4 14.4 18 18" },
    { d: "M6 6 3.5 8.5 6 11l2.5-2.5M18 18l-2.5 2.5L13 18l2.5-2.5" },
    { d: "M16 4.5a3.5 3.5 0 0 1 3.5 3.5M16 2a6 6 0 0 1 6 6" },
  ],
  foco: [
    { cx: 12, cy: 12, r: 2, fill: true },
    { cx: 12, cy: 12, r: 5.5 },
    { d: "M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21" },
  ],
  geocerca: [
    { d: "M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 1 1 0-17Z", dash: "2.4 2.4" },
    { d: "M12 8a2.6 2.6 0 0 1 2.6 2.6c0 2-2.6 4.6-2.6 4.6s-2.6-2.6-2.6-4.6A2.6 2.6 0 0 1 12 8Z" },
  ],
  mision: [
    { d: "M6.5 21V3.5" },
    { d: "M6.5 4h10.5l-2.2 3.6L17 11.2H6.5" },
    { d: "M3.5 21h6" },
  ],
  informe: [
    { d: "M6.5 3h7.5l4 4v14h-11.5Z" },
    { d: "M14 3v4h4" },
    { d: "M9.5 17.5v-3M12.2 17.5v-5.5M15 17.5v-2" },
  ],
  "marcador-anomalia": [
    { d: "M12 3 21 12l-9 9-9-9Z" },
    { cx: 12, cy: 12, r: 2.2, fill: true },
  ],
  "marcador-alerta": [
    { d: "M12 3.5 21.5 20h-19Z" },
    { d: "M12 10v4.5" },
    { cx: 12, cy: 17.2, r: 0.9, fill: true },
  ],
  "marcador-reporte": [
    { d: "M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11Z" },
    { cx: 12, cy: 10, r: 2.2, fill: true },
  ],
} satisfies Record<string, readonly Shape[]>;

export type IconName = keyof typeof ICONS;

/** Logotipo: párpado superior sobre la línea del horizonte y la pupila como sol que asoma. */
export const LOGO: readonly Shape[] = [
  { d: "M2.5 13.5C5.2 8.6 8.4 6 12 6s6.8 2.6 9.5 7.5" },
  { d: "M1.5 13.5h21" },
  { d: "M8.6 13.5a3.4 3.4 0 0 1 6.8 0" },
  { cx: 12, cy: 13.5, r: 1.1, fill: true },
  { d: "M6 17h12M9 20h6" },
];

const STROKE = 1.5;

function shapeToSvg(shape: Shape, color: string): string {
  const paint = shape.fill
    ? `fill="${color}" stroke="none"`
    : `fill="none" stroke="${color}" stroke-width="${STROKE}" stroke-linecap="round" stroke-linejoin="round"${"dash" in shape && shape.dash ? ` stroke-dasharray="${shape.dash}"` : ""}`;
  return "d" in shape
    ? `<path d="${shape.d}" ${paint}/>`
    : `<circle cx="${shape.cx}" cy="${shape.cy}" r="${shape.r}" ${paint}/>`;
}

/**
 * Marcador para MapLibre: disco del color de fondo con el icono encima, en `color`.
 * Se dibuja a 2x (pixelRatio 2) para que se vea nítido.
 */
export function markerSvg(name: IconName, color: string, background: string): string {
  const shapes = ICONS[name].map((s) => shapeToSvg(s, color)).join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 32 32">` +
    `<circle cx="16" cy="16" r="14" fill="${background}" stroke="${color}" stroke-width="1.5" opacity="0.94"/>` +
    `<g transform="translate(5 5) scale(0.9166)">${shapes}</g></svg>`
  );
}

/** El logotipo como SVG independiente (favicon, iconos del manifest). */
export function logoSvg(color: string, background: string, size: number, padding = 0.18): string {
  const inner = 24 * (1 - padding * 2);
  const offset = 24 * padding;
  const shapes = LOGO.map((s) => shapeToSvg(s, color)).join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24">` +
    `<rect width="24" height="24" fill="${background}"/>` +
    `<g transform="translate(${offset} ${offset}) scale(${inner / 24})">${shapes}</g></svg>`
  );
}
