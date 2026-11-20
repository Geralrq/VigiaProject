import type { ReactNode } from "react";
import { AppShell } from "@/features/auth/components/AppShell";

// Grupo de rutas privadas. Las públicas (p. ej. /a/[id]) viven fuera de este grupo, sin guardas.
export default function PrivateLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
