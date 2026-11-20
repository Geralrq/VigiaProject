// Copia el worker de MapLibre a public/maplibre/. Bajo Turbopack el worker que MapLibre
// resuelve con import.meta.url no carga (404 → mapa en blanco); se sirve como archivo estático
// y MapView lo registra con setWorkerUrl(). Se ejecuta en predev y prebuild.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const target = join(root, "public", "maplibre");
mkdirSync(target, { recursive: true });
copyFileSync(
  join(root, "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs"),
  join(target, "maplibre-gl-worker.mjs"),
);
