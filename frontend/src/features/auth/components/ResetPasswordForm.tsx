"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { useUpdatePassword } from "../api/useAuthActions";
import { translateAuthError } from "../errors";
import { useSession } from "../hooks/useSession";
import { MIN_PASSWORD_LENGTH, validateConfirmation, validateNewPassword } from "../validation";
import { AuthPage } from "./AuthPage";

export function ResetPasswordForm() {
  const router = useRouter();
  const { status, recovery } = useSession();
  const update = useUpdatePassword();
  const formRef = useRef<HTMLFormElement>(null);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirmation?: string }>({});
  // Al terminar se cierra la sesión de recuperación; sin esto se vería «enlace inválido» un instante.
  const [submitted, setSubmitted] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = {
      password: validateNewPassword(password) ?? undefined,
      confirmation: validateConfirmation(password, confirmation) ?? undefined,
    };
    setErrors(found);
    if (found.password || found.confirmation) {
      focusFirstInvalid(formRef.current);
      return;
    }
    setSubmitted(true);
    update.mutate(password, {
      onSuccess: () => router.replace("/login?aviso=clave-actualizada"),
      onError: () => setSubmitted(false),
    });
  }

  if (submitted) {
    return (
      <AuthPage title="Restablecer contraseña">
        <p role="status">Actualizando tu contraseña…</p>
      </AuthPage>
    );
  }

  if (status === "loading") {
    return (
      <AuthPage title="Restablecer contraseña">
        <p role="status">Verificando el enlace…</p>
      </AuthPage>
    );
  }

  // Solo se permite fijar la contraseña si la sesión nació del enlace (evento PASSWORD_RECOVERY).
  if (!recovery) {
    return (
      <AuthPage title="Enlace no válido">
        <p role="alert">
          El enlace venció, ya se usó o no corresponde a una recuperación de contraseña. Pide uno
          nuevo.
        </p>
        <p>
          <Link href="/recuperar">Pedir un enlace nuevo</Link>
        </p>
      </AuthPage>
    );
  }

  return (
    <AuthPage title="Restablecer contraseña" lede="Elige una contraseña nueva para tu cuenta.">
      <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Restablecer contraseña">
        <TextField
          label="Contraseña nueva"
          name="password"
          type="password"
          autoComplete="new-password"
          hint={`Mínimo ${MIN_PASSWORD_LENGTH} caracteres.`}
          value={password}
          error={errors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Repite la contraseña nueva"
          name="confirmation"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          error={errors.confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
        />
        {update.isError && (
          <p role="alert" className="error">
            {translateAuthError(update.error, "reset")}
          </p>
        )}
        <button type="submit" className="primary" disabled={update.isPending}>
          {update.isPending ? "Guardando…" : "Guardar contraseña"}
        </button>
      </form>
    </AuthPage>
  );
}
