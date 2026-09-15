<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Crop, Keyboard, Scan, Power, FolderOpen } from "lucide-vue-next";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { native, rpc } from "../lib/api";

defineProps<{ error: string; busy: boolean; result: string }>();
const emit = defineEmits<{ capture: []; pin: []; import: [] }>();
interface Preferences {
  captureShortcut: string;
  pinShortcut: string;
  autoDetect: boolean;
  autostart: boolean;
  shortcutsSupported: boolean;
  warning?: string;
  directCapture?: { state: string; message: string };
}
const values = ref<Preferences>({
  captureShortcut: "F1",
  pinShortcut: "F2",
  autoDetect: true,
  autostart: true,
  shortcutsSupported: false,
});
const saved = ref(""),
  message = ref(""),
  failure = ref(""),
  loading = ref(true),
  saving = ref(false);
const recording = ref<"captureShortcut" | "pinShortcut" | null>(null);
const enabling = ref(false);
const directCapture = ref<Preferences["directCapture"]>();
const dirty = computed(() => JSON.stringify(values.value) !== saved.value);
async function enableDirectCapture() {
  enabling.value = true;
  failure.value = "";
  try {
    directCapture.value = await rpc("enable_direct_capture");
    if (directCapture.value?.state === "enabling") {
      const loaded = await rpc<Preferences>("settings_get");
      directCapture.value = loaded.directCapture;
    }
  } catch (e) {
    failure.value = String(e);
  } finally {
    enabling.value = false;
  }
}
function dragWindow(event: PointerEvent) {
  if (
    native &&
    event.button === 0 &&
    !(event.target as HTMLElement).closest("button")
  )
    getCurrentWindow().startDragging();
}
let unlisten: undefined | (() => void),
  disposed = false;
watch(recording, (value) => {
  if (native)
    invoke("record_shortcut", { active: !!value }).catch((e) => {
      failure.value = String(e);
    });
});
onBeforeUnmount(() => {
  disposed = true;
  unlisten?.();
  if (native) invoke("record_shortcut", { active: false });
});
const shortcuts = [
  {
    key: "captureShortcut" as const,
    name: "截图",
    description: "冻结屏幕，选择区域并标注",
  },
  {
    key: "pinShortcut" as const,
    name: "贴图",
    description: "将剪贴板图片贴在屏幕上",
  },
];
function label(value: string) {
  return (
    value
      .replace(/<Primary>|<Control>/g, "Ctrl + ")
      .replace(/<Alt>/g, "Alt + ")
      .replace(/<Shift>/g, "Shift + ")
      .replace(/<Super>/g, "Super + ") || "未设置"
  );
}
function record(e: KeyboardEvent, key: "captureShortcut" | "pinShortcut") {
  if (recording.value !== key) return;
  e.preventDefault();
  e.stopPropagation();
  if (e.key === "Escape") {
    recording.value = null;
    return;
  }
  if (["Control", "Alt", "Shift", "Meta"].includes(e.key) || e.isComposing)
    return;
  if (e.key === "Backspace" || e.key === "Delete") values.value[key] = "";
  else {
    if (!(e.ctrlKey || e.altKey || e.metaKey || /^F\d+$/.test(e.key))) {
      failure.value = "请按功能键，或包含 Ctrl、Alt、Super 的组合键。";
      return;
    }
    const names: Record<string, string> = {
      " ": "space",
      ArrowUp: "Up",
      ArrowDown: "Down",
      ArrowLeft: "Left",
      ArrowRight: "Right",
      Enter: "Return",
    };
    values.value[key] =
      (e.ctrlKey ? "<Control>" : "") +
      (e.altKey ? "<Alt>" : "") +
      (e.shiftKey ? "<Shift>" : "") +
      (e.metaKey ? "<Super>" : "") +
      (names[e.key] || (e.key.length === 1 ? e.key.toLowerCase() : e.key));
  }
  failure.value = "";
  message.value = "";
  recording.value = null;
}
async function save() {
  saving.value = true;
  failure.value = "";
  message.value = "";
  try {
    values.value = await rpc<Preferences>("settings_save", { ...values.value });
    saved.value = JSON.stringify(values.value);
    message.value = native
      ? "设置已保存，快捷键已生效。"
      : "预览设置已保存；全局快捷键在桌面版生效。";
  } catch (e) {
    failure.value = String(e);
  } finally {
    saving.value = false;
  }
}
onMounted(async () => {
  try {
    if (native) {
      const stop = await listen<string>("shortcut-recorded", (event) => {
        if (recording.value) {
          values.value[recording.value] = event.payload;
          recording.value = null;
        }
      });
      if (disposed) {
        stop();
        return;
      }
      unlisten = stop;
    }
    values.value = await rpc<Preferences>("settings_get");
    directCapture.value = values.value.directCapture;
    delete values.value.directCapture;
    failure.value = values.value.warning || "";
    saved.value = JSON.stringify(values.value);
  } catch (e) {
    failure.value = String(e);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="settings-page">
    <header class="settings-heading" @pointerdown="dragWindow">
      <div class="settings-mark"><Crop :size="25" aria-hidden="true" /></div>
      <div>
        <h1>Linger 设置</h1>
      </div>
      <span class="resident-state"
        ><i></i>{{ native ? "后台运行中" : "界面预览" }}</span
      >
    </header>
    <section aria-labelledby="shortcuts-heading">
      <h2 id="shortcuts-heading">
        <Keyboard :size="17" aria-hidden="true" />快捷键
      </h2>
      <div class="settings-group">
        <div v-for="item in shortcuts" :key="item.key" class="setting-row">
          <div>
            <h3>{{ item.name }}</h3>
            <p>{{ item.description }}</p>
          </div>
          <button
            class="shortcut-input"
            :class="{ recording: recording === item.key }"
            :disabled="
              loading || saving || (native && !values.shortcutsSupported)
            "
            :aria-label="`设置${item.name}快捷键`"
            title="点击录入快捷键；Esc 取消，Backspace 清除"
            @click="recording = item.key"
            @keydown="record($event, item.key)"
            @blur="recording = null"
          >
            {{
              recording === item.key ? "请按快捷键…" : label(values[item.key])
            }}
          </button>
        </div>
      </div>
      <p
        v-if="native && !values.shortcutsSupported && !loading"
        class="section-help"
      >
        当前桌面请在系统键盘设置中配置快捷键。
      </p>
    </section>
    <section aria-labelledby="capture-heading">
      <h2 id="capture-heading"><Scan :size="17" aria-hidden="true" />截图</h2>
      <div class="settings-group">
        <div
          v-if="
            native && directCapture && directCapture.state !== 'unsupported'
          "
          class="capture-setup"
        >
          <div>
            <h3>直接进入截图</h3>
            <p>{{ directCapture.message }}</p>
            <p v-if="['disabled', 'needs-login'].includes(directCapture.state)">
              启用 Linger 桌面扩展，允许应用读取单次屏幕截图。
            </p>
          </div>
          <button
            v-if="
              ['disabled', 'needs-login', 'enabling'].includes(
                directCapture.state,
              )
            "
            class="secondary compact"
            :disabled="enabling"
            @click="enableDirectCapture"
          >
            {{ enabling ? "启用中…" : "启用直接截图" }}
          </button>
          <span
            v-else-if="directCapture.state === 'ready'"
            class="capture-ready"
            >已就绪</span
          >
        </div>
        <label class="setting-row"
          ><div>
            <h3>自动识别容器区域</h3>
            <p>悬停识别面板、卡片与窗口内的矩形区域</p>
          </div>
          <input
            v-model="values.autoDetect"
            class="setting-switch"
            type="checkbox"
            role="switch"
            :disabled="loading || saving"
        /></label>
      </div>
    </section>
    <section aria-labelledby="general-heading">
      <h2 id="general-heading">
        <Power :size="17" aria-hidden="true" />后台运行
      </h2>
      <div class="settings-group">
        <label class="setting-row"
          ><div>
            <h3>登录后自动启动</h3>
            <p>静默启动到托盘，不弹出设置窗口</p>
          </div>
          <input
            v-model="values.autostart"
            class="setting-switch"
            type="checkbox"
            role="switch"
            :disabled="loading || saving"
        /></label>
      </div>
    </section>
    <div class="settings-feedback" aria-live="polite">
      <p v-if="error || failure" class="settings-error" role="alert">
        {{ error || failure }}
      </p>
      <p v-else-if="busy">正在截取屏幕…</p>
      <p v-else-if="message || result">{{ message || result }}</p>
      <p v-else-if="dirty && !loading">有未保存的更改</p>
    </div>
    <footer class="settings-footer">
      <button
        class="secondary compact"
        :disabled="busy || saving || !!recording"
        @click="emit('capture')"
      >
        测试截图
      </button>
      <button class="settings-import" @click="emit('import')">
        <FolderOpen :size="15" aria-hidden="true" />打开图片
      </button>
      <button
        v-if="native"
        class="secondary compact settings-hide"
        @click="getCurrentWindow().hide()"
      >
        收起到托盘
      </button>
      <button
        class="primary"
        :disabled="loading || saving || !dirty || !!recording"
        @click="save"
      >
        {{ saving ? "保存中…" : "保存设置" }}
      </button>
    </footer>
    <p class="settings-version">Linger 截图 0.4.1</p>
  </main>
</template>
