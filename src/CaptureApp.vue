<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { Crop, Pin, AppWindow, FolderOpen, X } from "lucide-vue-next";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { rpc, native, type Shot } from "./lib/api";
import CaptureOverlay from "./components/CaptureOverlay.vue";
import PinWindow from "./components/PinWindow.vue";
import "./capture.css";
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
  shot.value = item;
  src.value = (await rpc<{ data: string }>("image", { id: item.id })).data;
  overlay.value = true;
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
function key(e: KeyboardEvent) {
  if (overlay.value) return;
  if (e.key === "F1") {
    e.preventDefault();
    start(e.shiftKey);
  }
  if (e.key === "F2") {
    e.preventDefault();
    clipboardPin();
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
  window.addEventListener("keydown", key);
  if (native)
    unlisten = await listen<string>("capture-error", (event) => {
      error.value = event.payload;
      busy.value = false;
    });
});
onBeforeUnmount(() => {
  unlisten?.();
  window.removeEventListener("keydown", key);
});
</script>
<template>
  <PinWindow v-if="pinId" :id="pinId" />
  <CaptureOverlay
    v-else-if="overlay"
    :src="src"
    :shot="shot"
    @close="close"
    @saved="result = '已完成截图'"
  />
  <main v-else class="launcher">
    <div class="launcher-brand">
      <Crop :size="23" aria-hidden="true" /><span>Linger 截图</span>
    </div>
    <div class="launcher-actions">
      <button class="primary" :disabled="busy" @click="start()">
        <Crop :size="17" aria-hidden="true" />{{ busy ? "正在截图…" : "截图"
        }}<kbd>F1</kbd>
      </button>
      <button class="secondary" :disabled="busy" @click="clipboardPin">
        <Pin :size="17" aria-hidden="true" />贴图<kbd>F2</kbd>
      </button>
    </div>
    <p class="launcher-status" role="status">
      {{ busy ? "请完成系统截图确认…" : "就绪" }}
    </p>
    <div class="launcher-links">
      <button :disabled="busy" @click="start(true)">
        <AppWindow :size="14" aria-hidden="true" />系统窗口截图
      </button>
      <button @click="file?.click()">
        <FolderOpen :size="14" aria-hidden="true" />打开图片
      </button>
      <button v-if="native" @click="getCurrentWindow().hide()">
        <X :size="14" aria-hidden="true" />收起
      </button>
    </div>
    <p v-if="error" class="launcher-error" role="alert">{{ error }}</p>
    <p v-if="result" role="status">{{ result }}</p>
    <input
      ref="file"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      class="visually-hidden"
      aria-label="打开图片"
      @change="importImage"
    />
  </main>
</template>
