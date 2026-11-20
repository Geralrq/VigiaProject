"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { safeNext } from "@/shared/auth/access";
import { useSignIn } from "../api/useAuthActions";
import { useSession } from "../hooks/useSession";

export function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const { status } = useSession();
  const signIn = useSignIn();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (status === "authed") router.replace(next);
  }, [status, next, router]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    signIn.mutate({ email, password });
  }

  return (
    <main className="auth-page">
      <h1>Vigía</h1>
      <p className="lede">
        Alerta temprana de deforestación e incendios. Ingresa con tu cuenta para ver el centro de
        comando.
      </p>
      <form
        onSubmit={onSubmit}
        aria-label="Iniciar sesión"
        aria-describedby={signIn.isError ? "login-error" : undefined}
      >
        <div className="form-field">
          <label htmlFor="email">Correo electrónico</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            spellCheck={false}
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="form-field">
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {signIn.isError && (
          <p id="login-error" role="alert" className="error">
            No se pudo iniciar sesión. Revisa tu correo y contraseña.
          </p>
        )}
        <button type="submit" className="primary" disabled={signIn.isPending}>
          {signIn.isPending ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </main>
  );
}
