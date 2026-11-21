"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { safeNext } from "@/shared/auth/access";
import { TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { useSignIn } from "../api/useAuthActions";
import { translateAuthError } from "../errors";
import { useSession } from "../hooks/useSession";
import { validateEmail } from "../validation";
import { AuthPage } from "./AuthPage";

const NOTICES: Record<string, string> = {
  "clave-actualizada": "Tu contraseña se actualizó. Ingresa con la nueva.",
  "cuenta-creada": "Tu cuenta quedó creada. Ingresa para continuar.",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const notice = NOTICES[params.get("aviso") ?? ""];
  const { status } = useSession();
  const signIn = useSignIn();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});

  useEffect(() => {
    if (status === "authed") router.replace(next);
  }, [status, next, router]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = {
      email: validateEmail(email) ?? undefined,
      password: password ? undefined : "Escribe tu contraseña.",
    };
    setErrors(found);
    if (found.email || found.password) {
      focusFirstInvalid(formRef.current);
      return;
    }
    signIn.mutate({ email: email.trim(), password });
  }

  return (
    <AuthPage
      title="Iniciar sesión"
      lede="Alerta temprana de deforestación e incendios. Ingresa para ver el centro de comando."
    >
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Iniciar sesión">
        <TextField
          label="Correo electrónico"
          name="email"
          type="email"
          autoComplete="email"
          spellCheck={false}
          value={email}
          error={errors.email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Contraseña"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          error={errors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {signIn.isError && (
          <p role="alert" className="error">
            {translateAuthError(signIn.error, "login")}
          </p>
        )}
        <button type="submit" className="primary" disabled={signIn.isPending}>
          {signIn.isPending ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
      <ul className="auth-links">
        <li>
          <Link href="/recuperar">Olvidé mi contraseña</Link>
        </li>
        <li>
          <Link href="/registro">Crear una cuenta</Link>
        </li>
      </ul>
    </AuthPage>
  );
}
