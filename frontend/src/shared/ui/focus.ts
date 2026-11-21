/**
 * Lleva el foco al primer campo inválido tras validar (cuando React ya pintó el error).
 * Reconoce campos con aria-invalid y avisos de error enfocables marcados con data-invalid.
 */
export function focusFirstInvalid(root: ParentNode | null): void {
  requestAnimationFrame(() => {
    root?.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalid="true"]')?.focus();
  });
}
