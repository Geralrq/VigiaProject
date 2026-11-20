import { Suspense } from "react";
import { LoginForm } from "@/features/auth/components/LoginForm";

export const metadata = { title: "Iniciar sesión · Vigía" };

export default function LoginPage() {
  return (
    <Suspense fallback={<p role="status" className="page-center">Cargando…</p>}>
      <LoginForm />
    </Suspense>
  );
}
