import Link from "next/link";

export const metadata = { title: "Alerta no encontrada · Vigía", robots: { index: false } };

export default function AlertNotFound() {
  return (
    <main className="auth-page">
      <p className="wordmark">Vigía</p>
      <h1>No encontramos esta alerta</h1>
      <p className="lede">
        El enlace puede estar incompleto o la alerta ya no existe. Revisa que la dirección esté
        completa.
      </p>
      <p>
        <Link href="/login">Ir a Vigía</Link>
      </p>
    </main>
  );
}
