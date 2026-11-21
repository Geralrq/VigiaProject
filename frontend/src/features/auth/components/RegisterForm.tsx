"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { TextField } from "@/shared/ui/fields";
import { focusFirstInvalid } from "@/shared/ui/focus";
import { useSignUp } from "../api/useAuthActions";
import { translateAuthError } from "../errors";
import { useSession } from "../hooks/useSession";
import {
  MIN_PASSWORD_LENGTH,
  validateConfirmation,
  validateEmail,
  validateName,
  validateNewPassword,
} from "../validation";
import { AuthPage } from "./AuthPage";

type Errors = Partial<Record<"name" | "email" | "password" | "confirmation", string>>;

export function RegisterForm() {
  const router = useRouter();
  const { status } = useSession();
  const signUp = useSignUp();
  const formRef = useRef<HTMLFormElement>(null);
  const wantsProfile = useRef(false); // true solo si la sesión nace de este registro
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<Errors>({});

  useEffect(() => {
    // Con sesión al instante → /perfil (nombre y ubicación). Quien ya estaba dentro → /mapa.
    if (status === "authed") router.replace(wantsProfile.current ? "/perfil" : "/mapa");
  }, [status, router]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found: Errors = {
      name: validateName(name) ?? undefined,
      email: validateEmail(email) ?? undefined,
      password: validateNewPassword(password) ?? undefined,
      confirmation: validateConfirmation(password, confirmation) ?? undefined,
    };
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      focusFirstInvalid(formRef.current);
      return;
    }
    wantsProfile.current = true;
    signUp.mutate(
      { name: name.trim(), email: email.trim(), password },
      { onError: () => (wantsProfile.current = false) },
    );
  }

  if (signUp.isSuccess && !signUp.data.sessionStarted) {
    return (
      <AuthPage title="Revisa tu correo">
        <p role="status">
          Te enviamos un enlace para confirmar tu cuenta. Ábrelo y luego inicia sesión. Si no lo ves,
          busca en la carpeta de spam.
        </p>
        <p>
          <Link href="/login?aviso=cuenta-creada">Ir a iniciar sesión</Link>
        </p>
      </AuthPage>
    );
  }

  return (
    <AuthPage title="Crear una cuenta" lede="Con tu cuenta puedes reportar problemas ambientales y verificar alertas cerca de ti.">
      <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Crear una cuenta">
        <TextField
          label="Nombre"
          name="name"
          autoComplete="name"
          value={name}
          error={errors.name}
          onChange={(e) => setName(e.target.value)}
        />
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
          autoComplete="new-password"
          hint={`Mínimo ${MIN_PASSWORD_LENGTH} caracteres.`}
          value={password}
          error={errors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Repite la contraseña"
          name="confirmation"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          error={errors.confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
        />
        {signUp.isError && (
          <p role="alert" className="error">
            {translateAuthError(signUp.error, "signup")}
          </p>
        )}
        <button type="submit" className="primary" disabled={signUp.isPending}>
          {signUp.isPending ? "Creando cuenta…" : "Crear cuenta"}
        </button>
      </form>
      <ul className="auth-links">
        <li>
          <Link href="/login">Ya tengo una cuenta</Link>
        </li>
      </ul>
    </AuthPage>
  );
}
