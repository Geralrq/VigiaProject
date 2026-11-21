import type { ReactNode } from "react";

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
    <main className="auth-page">
      <p className="wordmark">Vigía</p>
      <h1>{title}</h1>
      {lede && <p className="lede">{lede}</p>}
      {children}
    </main>
  );
}
