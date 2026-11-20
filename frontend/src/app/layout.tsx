import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/shared/providers";
import "@/shared/styles/tokens.css";
import "@/shared/styles/base.css";

// Archivo con eje de ancho (títulos semi-expandidos); Plex Mono solo para instrumentos.
const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  display: "swap",
  variable: "--font-archivo",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Vigía",
  description: "Inteligencia ambiental y alerta temprana",
};

export const viewport: Viewport = { colorScheme: "dark", themeColor: "#0c1512" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={`${archivo.variable} ${plexMono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
