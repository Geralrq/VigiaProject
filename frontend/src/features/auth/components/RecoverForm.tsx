"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { useRequestPasswordReset } from "../api/useAuthActions";
import { isTransientAuthError, translateAuthError } from "../errors";
import { validateEmail } from "../validation";
import { AuthPage } from "./AuthPage";

export function RecoverForm() {
  const request = useRequestPasswordReset();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateEmail(email) ?? undefined;
    setError(invalid);
    if (invalid) {
      focusFirstInvalid(formRef.current);
      return;
    }
    request.mutate(email.trim());
  }

  // Respuesta neutra: igual exista o no la cuenta. Solo se muestran fallos que no delatan nada
  // (sin conexión, demasiados intentos).
  const done = request.isSuccess || (request.isError && !isTransientAuthError(request.error));

  if (done) {
    return (
      <AuthPage title="Revisa tu correo">
        <p role="status">
          Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la
          contraseña. Puede tardar unos minutos; revisa también la carpeta de spam.
        </p>
        <p>
          <Link href="/login">Volver a iniciar sesión</Link>
        </p>
      </AuthPage>
    );
  }

  return (
    <AuthPage title="Recuperar contraseña" lede="Escribe el correo de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.">
      <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Recuperar contraseña">
        <TextField
          label="Correo electrónico"
          name="email"
          type="email"
          autoComplete="email"
          spellCheck={false}
          value={email}
          error={error}
          onChange={(e) => setEmail(e.target.value)}
        />
        {request.isError && (
          <p role="alert" className="error">
            {translateAuthError(request.error, "recover")}
          </p>
        )}
        <button type="submit" className="primary" disabled={request.isPending}>
          {request.isPending ? "Enviando…" : "Enviar enlace"}
        </button>
      </form>
      <ul className="auth-links">
        <li>
          <Link href="/login">Volver a iniciar sesión</Link>
        </li>
      </ul>
    </AuthPage>
  );
}
