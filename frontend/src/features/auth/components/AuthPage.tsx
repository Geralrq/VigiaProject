import type { ReactNode } from "react";
import { Logo } from "@/shared/ui/icons/Icon";

/** Marco de las páginas públicas de cuenta (login, registro, recuperación). */
export function AuthPage({
  title,
  lede,
  children,
}: {
  title: string;
  lede?: string;
  children: ReactNode;
}) {
  return (
    <div className="auth-screen">
      {/* Cuadrícula cartográfica de fondo: decorativa, se desplaza muy despacio. */}
      <div className="carto-grid" aria-hidden="true" />
      <main className="auth-page">
        <p className="wordmark">
          <Logo size={32} />
          <span>Vigía</span>
        </p>
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
        {children}
      </main>
    </div>
  );
}
