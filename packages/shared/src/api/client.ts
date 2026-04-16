const BASE_URL =
  (typeof process !== "undefined" && process.env.EXPO_PUBLIC_API_URL) ??
  "http://localhost:8000";

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) {
    throw new Error(`暫時連不上，請稍後再試（${res.status}）`);
  }
  return res.json() as Promise<T>;
}
