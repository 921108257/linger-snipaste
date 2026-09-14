<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { rpc, native, type Shot } from "./lib/api";
import CaptureOverlay from "./components/CaptureOverlay.vue";
import PinWindow from "./components/PinWindow.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import type { Region } from "./lib/regions";
import "./capture.css";
import "./settings.css";
const query = new URLSearchParams(location.search),
  overlayId = query.get("overlay"),
  pinId = query.get("pin");
const overlay = ref(false),
  src = ref(""),
  shot = ref<Shot>(),
  error = ref(""),
  busy = ref(false),
  file = ref<HTMLInputElement>(),
  result = ref("");
let unlisten: undefined | (() => void);
const regions = ref<Region[]>([]),
  detecting = ref(false),
  detectionError = ref("");
async function start(interactive = false) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  result.value = "";
  try {
    if (!native)
      throw new Error("请使用桌面版截图；浏览器预览可打开图片进行编辑。");
    await invoke("begin_capture", { interactive });
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e);
  } finally {
    busy.value = false;
  }
}
async function open(item: Shot) {
  regions.value = [];
  detectionError.value = "";
  shot.value = item;
  src.value = (await rpc<{ data: string }>("image", { id: item.id })).data;
  overlay.value = true;
  if (native && item.auto_detect !== false) {
    detecting.value = true;
    rpc<Region[]>("detect_regions", { id: item.id })
      .then((value) => {
        if (shot.value?.id === item.id) regions.value = value;
      })
      .catch(() => {
        detectionError.value = "区域识别暂不可用，请拖动框选。";
      })
      .finally(() => {
        detecting.value = false;
      });
  }
}
async function close() {
  overlay.value = false;
  if (native && overlayId) await getCurrentWindow().close();
}
async function importImage(e: Event) {
  const selected = (e.target as HTMLInputElement).files?.[0];
  if (!selected) return;
  try {
    const data = await new Promise<string>((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result));
      r.onerror = reject;
      r.readAsDataURL(selected);
    });
    await open(await rpc<Shot>("import", { data }));
  } catch (e) {
    error.value = String(e);
  } finally {
    (e.target as HTMLInputElement).value = "";
  }
}
async function clipboardPin() {
  try {
    const item = await rpc<Shot>("import_clipboard");
    if (native)
      await invoke("pin_image", {
        id: item.id,
        width: item.width,
        height: item.height,
      });
    else window.open(`?pin=${item.id}`, "_blank", "popup,width=640,height=480");
  } catch (e) {
    error.value = String(e);
  }
}
onMounted(async () => {
  if (pinId) return;
  if (overlayId) {
    try {
      await open(await rpc<Shot>("metadata", { id: overlayId }));
    } catch (e) {
      error.value = String(e);
      if (native) await invoke("overlay_ready");
    }
    return;
  }
  if (import.meta.env.DEV && query.has("sample")) {
    src.value = (await import("./assets/sample.svg")).default;
    overlay.value = true;
  }
  if (native)
    unlisten = await listen<string>("capture-error", (event) => {
      error.value = event.payload;
      busy.value = false;
    });
});
onBeforeUnmount(() => {
  unlisten?.();
});
</script>
<template>
  <PinWindow v-if="pinId" :id="pinId" />
  <CaptureOverlay
    v-else-if="overlay"
    :src="src"
    :shot="shot"
    :regions="regions"
    :detecting="detecting"
    :detection-error="detectionError"
    @close="close"
    @saved="result = '已完成截图'"
  />
  <template v-else>
    <SettingsPanel
      :error="error"
      :busy="busy"
      :result="result"
      @capture="start()"
      @pin="clipboardPin"
      @import="file?.click()"
    />
    <input
      ref="file"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      class="visually-hidden"
      aria-label="打开图片"
      @change="importImage"
    />
  </template>
</template>
