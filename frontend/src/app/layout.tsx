import type { ReactNode } from "react";
import { Providers } from "@/shared/providers";

export const metadata = { title: "Vigía" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}