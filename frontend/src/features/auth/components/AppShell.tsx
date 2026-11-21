"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ROLE_LABELS, navFor, rolesForPath } from "@/shared/auth/access";
import { Icon, Logo } from "@/shared/ui/icons/Icon";
import { UiIcon, type UiIconName } from "@/shared/ui/icons/ui";
import { ErrorState, Skeleton } from "@/shared/ui/states";
import { useMe } from "../api/useMe";
import { useSignOut } from "../api/useAuthActions";
import { useSession } from "../hooks/useSession";

// Icono de cada destino del menú (Phosphor para interfaz; propio para lo del dominio).
const NAV_ICONS: Record<string, UiIconName | "mision"> = {
  "/mapa": "mapa",
  "/reportar": "reportar",
  "/misiones": "mision",
  "/inspecciones": "inspecciones",
  "/ranking": "ranking",
  "/perfil": "perfil",
};

function NavIcon({ href }: { href: string }) {
  const name = NAV_ICONS[href];
  if (!name) return null;
  return name === "mision" ? <Icon name="mision" /> : <UiIcon name={name} />;
}

/** Carcasa de las páginas privadas: guarda de sesión y de rol por ruta, y menú por rol. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useSession();
  const me = useMe();
  const signOut = useSignOut();

  useEffect(() => {
    if (status === "anon") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, pathname, router]);

  let body: ReactNode;
  if (status !== "authed" || me.isPending) {
    body = (
      <div className="page">
        <Skeleton label="Cargando tu sesión…" lines={4} />
      </div>
    );
  } else if (me.isError) {
    body = (
      <div className="page">
        <ErrorState message="No se pudo cargar tu perfil." onRetry={() => me.refetch()} />
      </div>
    );
  } else if (!rolesForPath(pathname).includes(me.data.role)) {
    body = (
      <div className="page-center" role="alert">
        <h2>Sin acceso</h2>
        <p>Tu rol ({ROLE_LABELS[me.data.role]}) no tiene permiso para ver esta página.</p>
        <Link href="/mapa">Volver al centro de comando</Link>
      </div>
    );
  } else {
    body = children;
  }

  const items = me.data ? navFor(me.data.role) : [];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <header className="app-header">
        <Link href="/mapa" className="wordmark">
          <Logo size={26} />
          <span>Vigía</span>
        </Link>
        {items.length > 0 && (
          <nav className="app-nav" aria-label="Principal">
            <ul>
              {items.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={pathname.startsWith(item.href) ? "page" : undefined}
                  >
                    <NavIcon href={item.href} />
                    <span>{item.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
        {me.data && (
          <div className="app-user">
            <span>
              {me.data.name} <span className="role">({ROLE_LABELS[me.data.role]})</span>
            </span>
            <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
              <UiIcon name="salir" size={18} /> Cerrar sesión
            </button>
          </div>
        )}
      </header>
      <main id="contenido" className="app-main" tabIndex={-1}>
        {body}
      </main>
    </div>
  );
}
