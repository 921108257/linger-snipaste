import { invoke, isTauri } from "@tauri-apps/api/core";
export const native = isTauri();
export interface Shot {
  id: string;
  name: string;
  width: number;
  height: number;
  bytes: number;
  created_at: string;
  captured_at: string | null;
  source: string;
  sha256: string;
  path: string;
  thumbnail: string;
  auto_detect?: boolean;
}
export interface Status {
  state: "ready" | "requesting";
  backend: string;
}
export async function rpc<T>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  if (native) return invoke<T>("rpc", { method, params });
  const { browserRpc } = await import("./browser-store");
  return browserRpc(method, params) as Promise<T>;
}
