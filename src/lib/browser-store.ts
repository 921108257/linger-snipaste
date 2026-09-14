import type { Shot } from "./api";
// Browser preview edits imported images only; it has no desktop capture bridge.
const database = new Promise<IDBDatabase>((resolve, reject) => {
  const request = indexedDB.open("linger-image-preview", 1);
  request.onupgradeneeded = () =>
    request.result.createObjectStore("images", { keyPath: "id" });
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
});
async function record(id: string): Promise<Shot & { data: string }> {
  const db = await database;
  return new Promise((resolve, reject) => {
    const request = db.transaction("images").objectStore("images").get(id);
    request.onsuccess = () =>
      request.result
        ? resolve(request.result)
        : reject(new Error("图片已不存在，请重新打开。"));
    request.onerror = () => reject(request.error);
  });
}
export async function browserRpc(
  method: string,
  params: Record<string, unknown>,
): Promise<unknown> {
  if (method === "status") return { state: "ready", backend: "image-preview" };
  if (method === "import") {
    const data = String(params.data);
    const image = new Image();
    image.src = data;
    await image.decode();
    const id = crypto.randomUUID().replaceAll("-", "");
    const item = {
      id,
      data,
      name: "图片",
      width: image.naturalWidth,
      height: image.naturalHeight,
      created_at: new Date().toISOString(),
      captured_at: null,
      source: "import",
      bytes: data.length,
      sha256: "",
      path: "",
      thumbnail: "",
    };
    const db = await database;
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("images", "readwrite");
      tx.objectStore("images").put(item);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return item;
  }
  if (method === "image")
    return { data: (await record(String(params.id))).data };
  if (method === "metadata") return record(String(params.id));
  if (method === "clipboard") {
    const blob = await (
      await fetch((await record(String(params.id))).data)
    ).blob();
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    return { copied: true };
  }
  if (method === "import_clipboard") {
    for (const item of await navigator.clipboard.read()) {
      const type = item.types.find((t) => t.startsWith("image/"));
      if (!type) continue;
      const blob = await item.getType(type);
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
      return browserRpc("import", { data });
    }
    throw new Error("剪贴板中没有图片。");
  }
  throw new Error("请在桌面版使用截图功能；浏览器预览可打开图片进行编辑。");
}
