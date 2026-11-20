"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ROLE_LABELS, navFor, rolesForPath } from "@/shared/auth/access";
import { useMe } from "../api/useMe";
import { useSignOut } from "../api/useAuthActions";
import { useSession } from "../hooks/useSession";

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
    body = <p role="status" className="page-center">Cargando…</p>;
  } else if (me.isError) {
    body = (
      <div className="page-center" role="alert">
        <p className="error">No se pudo cargar tu perfil.</p>
        <button type="button" onClick={() => me.refetch()}>
          Reintentar
        </button>
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
      <header className="app-header">
        <h1>Vigía</h1>
        {items.length > 0 && (
          <nav className="app-nav" aria-label="Principal">
            <ul>
              {items.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={pathname.startsWith(item.href) ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
        {me.data && (
          <div className="app-user">
            <span>
              {me.data.name} · {ROLE_LABELS[me.data.role]}
            </span>
            <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
              Cerrar sesión
            </button>
          </div>
        )}
      </header>
      <div className="app-main">{body}</div>
    </div>
  );
}
