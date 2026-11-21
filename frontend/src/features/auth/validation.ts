export const MIN_PASSWORD_LENGTH = 8;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(email: string): string | null {
  if (!email.trim()) return "Escribe tu correo electrónico.";
  return EMAIL.test(email.trim()) ? null : "Escribe un correo válido, por ejemplo nombre@correo.com.";
}

export function validateNewPassword(password: string): string | null {
  if (!password) return "Escribe una contraseña.";
  return password.length >= MIN_PASSWORD_LENGTH
    ? null
    : `La contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres.`;
}

export function validateConfirmation(password: string, confirmation: string): string | null {
  if (!confirmation) return "Repite la contraseña.";
  return password === confirmation ? null : "Las contraseñas no coinciden.";
}

export function validateName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "Escribe tu nombre.";
  return trimmed.length <= 200 ? null : "El nombre es demasiado largo (máximo 200 caracteres).";
}
