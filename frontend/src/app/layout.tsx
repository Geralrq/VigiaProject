import type { ReactNode } from "react";
import { Providers } from "@/shared/providers";
import "@/shared/styles/tokens.css";
import "@/shared/styles/base.css";

export const metadata = {
  title: "Vigía",
  description: "Inteligencia ambiental y alerta temprana",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
