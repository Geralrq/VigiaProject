/** Lee un token de tokens.css en tiempo de ejecución (MapLibre/deck.gl no entienden var()). */
export function readToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Token numérico sin unidad (p. ej. "0.5") → número. */
export function readNumberToken(name: string): number {
  return Number(readToken(name));
}

/** Token con formato "r, g, b" → [r, g, b]. */
export function readRgbToken(name: string): [number, number, number] {
  const [r = 0, g = 0, b = 0] = readToken(name)
    .split(",")
    .map((part) => Number(part.trim()));
  return [r, g, b];
}
