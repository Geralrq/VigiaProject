// Single entry point for HTTP calls. Components never call fetch directly.
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}