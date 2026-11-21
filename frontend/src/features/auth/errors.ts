type AuthContext = "login" | "signup" | "recover" | "reset";

interface AuthErrorLike {
  code?: string;
  status?: number;
  message?: string;
  name?: string;
}

const NETWORK = "No hay conexión. Revisa tu internet e inténtalo de nuevo.";
const RATE_LIMIT = "Hiciste demasiados intentos. Espera unos minutos e inténtalo de nuevo.";
const GENERIC = "No se pudo completar la acción. Inténtalo de nuevo.";

/**
 * Traduce errores de Supabase Auth al español. Nunca dice si un correo existe: los casos que lo
 * delatarían (usuario ya registrado, correo desconocido) reciben mensajes neutros.
 */
export function translateAuthError(error: unknown, context: AuthContext): string {
  const e = (error ?? {}) as AuthErrorLike;
  const code = e.code ?? "";
  const message = (e.message ?? "").toLowerCase();

  if (e.name === "AuthRetryableFetchError" || message.includes("failed to fetch") || message.includes("network")) {
    return NETWORK;
  }
  if (code.includes("rate_limit") || e.status === 429 || message.includes("rate limit")) {
    return RATE_LIMIT;
  }
  if (code === "weak_password" || message.includes("password should")) {
    return "La contraseña es muy débil. Usa al menos 8 caracteres y evita contraseñas comunes.";
  }
  if (code === "same_password") {
    return "La contraseña nueva debe ser distinta de la anterior.";
  }
  if (code === "email_address_invalid" || message.includes("invalid email")) {
    return "Escribe un correo electrónico válido.";
  }
  if (code === "session_expired" || code === "session_not_found" || message.includes("session")) {
    return context === "reset"
      ? "El enlace venció o ya se usó. Pide uno nuevo en «Olvidé mi contraseña»."
      : "Tu sesión terminó. Inicia sesión de nuevo.";
  }
  if (context === "login") {
    if (code === "email_not_confirmed") {
      return "Confirma tu correo antes de ingresar. Revisa tu bandeja de entrada y la carpeta de spam.";
    }
    return "Correo o contraseña incorrectos.";
  }
  if (context === "signup") {
    // «User already registered» revelaría que el correo existe.
    return "No pudimos crear la cuenta con esos datos. Si ya tienes una, inicia sesión o recupera tu contraseña.";
  }
  return GENERIC;
}

/** true para errores que no delatan nada y que conviene mostrar aunque el flujo sea «neutro». */
export function isTransientAuthError(error: unknown): boolean {
  const message = translateAuthError(error, "recover");
  return message === NETWORK || message === RATE_LIMIT;
}
