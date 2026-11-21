import { getSupabase } from "@/shared/supabase/client";
import type { ProblemDetails } from "./types";

/**
 * Único punto de salida HTTP de la app: ningún componente llama fetch directo.
 * Todo pasa por hooks de React Query en features/<x>/api, que usan estas funciones.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  /** Cuerpo JSON. */
  body?: unknown;
  /** Cuerpo multipart (fotos). El navegador fija el Content-Type con su boundary. */
  form?: FormData;
  signal?: AbortSignal;
  /** "blob" para descargas binarias (PDF). Por defecto JSON. */
  as?: "json" | "blob";
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api${path}${qs ? `?${qs}` : ""}`;
}

async function readProblem(res: Response): Promise<string> {
  try {
    const problem = (await res.json()) as Partial<ProblemDetails>;
    return problem.detail || problem.title || `Error ${res.status}`;
  } catch {
    return `Error ${res.status}`;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const supabase = getSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers: Record<string, string> = {
    Accept: options.as === "blob" ? "application/pdf" : "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let body: BodyInit | undefined;
  if (options.form) body = options.form;
  else if (options.body !== undefined) body = JSON.stringify(options.body);

  let res: Response;
  try {
    res = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "No hay conexión con el servidor. Revisa tu internet e inténtalo de nuevo.");
  }

  if (res.status === 401) {
    // Sesión vencida o inválida: se cierra y los guardas de ruta llevan a /login.
    if (token) await supabase.auth.signOut();
    throw new ApiError(401, "Tu sesión terminó. Inicia sesión de nuevo.");
  }
  if (res.status === 403) {
    throw new ApiError(403, "No tienes permiso para esta acción.");
  }
  if (!res.ok) throw new ApiError(res.status, await readProblem(res));
  if (options.as === "blob") return (await res.blob()) as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal) =>
    apiRequest<T>(path, { query, signal }),
  getBlob: (path: string) => apiRequest<Blob>(path, { as: "blob" }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  postForm: <T>(path: string, form: FormData) => apiRequest<T>(path, { method: "POST", form }),
};

/** Reintentar solo errores transitorios: 401/403/404/422 no mejoran repitiendo. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [0, 401, 403, 404, 413, 422].includes(error.status)) return false;
  return failureCount < 2;
}
