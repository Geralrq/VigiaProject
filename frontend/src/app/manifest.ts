import type { MetadataRoute } from "next";

// Servido en /manifest.webmanifest. Los colores repiten --color-bg de tokens.css (el manifest no
// puede leer CSS): si cambian los tokens, actualizar aquí también.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vigía — alerta temprana ambiental",
    short_name: "Vigía",
    description: "Inteligencia ambiental y alerta temprana de deforestación e incendios.",
    lang: "es-CO",
    start_url: "/mapa",
    scope: "/",
    display: "standalone",
    background_color: "#0c1512",
    theme_color: "#0c1512",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
