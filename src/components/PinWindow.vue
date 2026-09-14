<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { Pin, Copy, X, Minus, Plus } from "lucide-vue-next";
import IconButton from "./IconButton.vue";
import { rpc, native } from "../lib/api";
import { getCurrentWindow } from "@tauri-apps/api/window";
const props = defineProps<{ id: string }>();
const src = ref(""),
  width = ref(0),
  height = ref(0),
  opacity = ref(100),
  zoom = ref(100),
  top = ref(true),
  error = ref("");
async function close() {
  if (native) await getCurrentWindow().close();
  else window.close();
}
async function copy() {
  try {
    await rpc("clipboard", { id: props.id });
  } catch (e) {
    error.value = String(e);
  }
}
function key(e: KeyboardEvent) {
  if (e.key === "Escape") close();
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
    e.preventDefault();
    copy();
  }
}
function wheel(e: WheelEvent) {
  zoom.value = Math.max(
    10,
    Math.min(500, zoom.value + (e.deltaY < 0 ? 10 : -10)),
  );
}
onMounted(async () => {
  try {
    src.value = (await rpc<{ data: string }>("image", { id: props.id })).data;
    const image = new Image();
    image.onload = () => {
      width.value = image.width;
      height.value = image.height;
    };
    image.src = src.value;
  } catch (e) {
    error.value = String(e);
  }
  window.addEventListener("keydown", key);
});
onBeforeUnmount(() => window.removeEventListener("keydown", key));
</script>
<template>
  <div class="pin-surface">
    <div class="pin-toolbar">
      <IconButton
        :icon="Pin"
        label="置顶"
        :active="top"
        @click="
          top = !top;
          native && getCurrentWindow().setAlwaysOnTop(top);
        "
      /><label
        >透明度<input
          v-model.number="opacity"
          type="range"
          min="10"
          max="100"
          aria-label="图片透明度" /></label
      ><IconButton
        :icon="Minus"
        label="缩小"
        @click="zoom = Math.max(10, zoom - 10)"
      /><span>{{ zoom }}%</span
      ><IconButton
        :icon="Plus"
        label="放大"
        @click="zoom = Math.min(500, zoom + 10)"
      /><IconButton :icon="Copy" label="复制图片" @click="copy" /><IconButton
        :icon="X"
        label="关闭贴图"
        @click="close"
      />
    </div>
    <div class="pin-image-scroll" @wheel.prevent="wheel">
      <img
        v-if="src"
        :src="src"
        :width="width"
        :height="height"
        alt="贴图"
        :style="{ opacity: opacity / 100, width: zoom + '%', height: 'auto' }"
      />
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>
