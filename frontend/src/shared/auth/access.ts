import type { Role } from "@/shared/api/types";

export const ALL_ROLES: readonly Role[] = [
  "CIUDADANO",
  "GUARDABOSQUES",
  "TECNICO",
  "AUTORIDAD",
  "ADMIN",
];

export const ROLE_LABELS: Record<Role, string> = {
  CIUDADANO: "Ciudadano",
  GUARDABOSQUES: "Guardabosques",
  TECNICO: "Técnico",
  AUTORIDAD: "Autoridad",
  ADMIN: "Administrador",
};

export interface NavItem {
  href: string;
  label: string;
  roles: readonly Role[];
}

/**
 * Fuente única de qué ve cada rol: el menú (navFor) y la guarda de ruta (rolesForPath) salen de
 * esta tabla, así que no pueden contradecirse. El backend sigue siendo quien autoriza de verdad.
 * Las páginas públicas (/login, /registro, /recuperar, /restablecer, /a/[id]) no están aquí.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/mapa", label: "Centro de comando", roles: ALL_ROLES },
  { href: "/reportar", label: "Reportar", roles: ALL_ROLES },
  { href: "/misiones", label: "Misiones", roles: ["CIUDADANO", "GUARDABOSQUES"] },
  { href: "/inspecciones", label: "Inspecciones", roles: ["TECNICO", "AUTORIDAD", "ADMIN"] },
  { href: "/ranking", label: "Ranking", roles: ALL_ROLES },
  { href: "/admin/usuarios", label: "Usuarios", roles: ["ADMIN"] },
  { href: "/perfil", label: "Mi perfil", roles: ALL_ROLES },
];

export function navFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => item.roles.includes(role));
}

/** Roles permitidos en una ruta según la tabla de navegación (sin entrada: cualquier sesión). */
export function rolesForPath(pathname: string): readonly Role[] {
  const item = NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  return item ? item.roles : ALL_ROLES;
}

/** Evita redirecciones abiertas: solo rutas internas. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/mapa";
}
