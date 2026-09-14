<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import Konva from "konva";
import {
  Square,
  Circle,
  MoveUpRight,
  Pencil,
  Type,
  Grid2X2,
  Undo2,
  Redo2,
  Pin,
  Copy,
  Download,
  X,
  Check,
  MousePointer2,
  Eraser,
  Scan,
  Trash2,
} from "lucide-vue-next";
import IconButton from "./IconButton.vue";
import { rpc, native, type Shot } from "../lib/api";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { regionsAt, type Region } from "../lib/regions";
const props = defineProps<{
  src: string;
  shot?: Shot;
  regions?: Region[];
  detecting?: boolean;
  detectionError?: string;
}>();
const hoverRegions = ref<Region[]>([]),
  hoverIndex = ref(0);
let clickedRegion: Region | undefined,
  unlistenPin: undefined | (() => void),
  disposed = false;
const hoverRegion = computed(() => hoverRegions.value[hoverIndex.value]);
function screenRegion(r: Region) {
  return {
    x: origin.x + r.x * imageWidth * scale,
    y: origin.y + r.y * imageHeight * scale,
    width: r.width * imageWidth * scale,
    height: r.height * imageHeight * scale,
  };
}
const hoverBox = computed(() => {
  viewport.value;
  return hoverRegion.value ? screenRegion(hoverRegion.value) : null;
});
function identify(p: { x: number; y: number }) {
  const candidates = regionsAt(
    props.regions || [],
    (p.x - origin.x) / (imageWidth * scale),
    (p.y - origin.y) / (imageHeight * scale),
  );
  if (JSON.stringify(candidates) !== JSON.stringify(hoverRegions.value))
    hoverIndex.value = 0;
  hoverRegions.value = candidates;
}
function cycleRegion(e: WheelEvent) {
  if (selection.value || dragging.value || !hoverRegions.value.length) return;
  e.preventDefault();
  hoverIndex.value = Math.max(
    0,
    Math.min(
      hoverRegions.value.length - 1,
      hoverIndex.value + (e.deltaY > 0 ? 1 : -1),
    ),
  );
}
watch(
  () => props.regions,
  () => {
    if (ready.value && !selection.value && !dragging.value)
      identify(cursor.value);
  },
);
const emit = defineEmits<{ close: []; saved: [Shot] }>();
const host = ref<HTMLDivElement>(),
  toolbar = ref<HTMLDivElement>(),
  textInput = ref<HTMLInputElement>();
const selection = ref<{
  x: number;
  y: number;
  width: number;
  height: number;
} | null>(null);
const viewport = ref({ width: innerWidth, height: innerHeight });
const dragging = ref(false),
  tool = ref("select"),
  color = ref("#ef5350"),
  stroke = ref(3),
  ready = ref(false),
  busy = ref(false),
  error = ref("");
const text = ref(""),
  textPosition = ref<{ x: number; y: number } | null>(null),
  cursor = ref({ x: 0, y: 0 });
const undoCount = ref(0),
  redoCount = ref(0);
const objectSelected = ref(false),
  eraseSize = ref(24),
  canvasCursor = ref("crosshair");
const toolbarSize = ref({ width: 580, height: 46 });
let toolbarObserver: ResizeObserver;
let objectDrag: {
  node: Konva.Node;
  start: { x: number; y: number };
  position: { x: number; y: number };
} | null = null;
let transforming = false,
  editingText: Konva.Text | null = null;
const tools = [
  { id: "rect", icon: Square, label: "矩形" },
  { id: "ellipse", icon: Circle, label: "椭圆" },
  { id: "arrow", icon: MoveUpRight, label: "箭头" },
  { id: "pen", icon: Pencil, label: "画笔" },
  { id: "text", icon: Type, label: "文字" },
  { id: "mosaic", icon: Grid2X2, label: "马赛克" },
  { id: "eraser", icon: Eraser, label: "橡皮擦" },
];
const colors = [
  "#ef5350",
  "#ffcb45",
  "#40b982",
  "#4c8bff",
  "#ffffff",
  "#25282d",
];
let stage: Konva.Stage,
  layer: Konva.Layer,
  background: Konva.Image,
  annotations: Konva.Group,
  transform: Konva.Transformer;
let image: HTMLImageElement,
  scale = 1,
  origin = { x: 0, y: 0 },
  imageWidth = 0,
  imageHeight = 0;
let anchor = { x: 0, y: 0 },
  shape: Konva.Shape | null = null,
  history: Konva.Group[] = [],
  historyIndex = -1,
  observer: ResizeObserver;
let moveStart: {
  x: number;
  y: number;
  selection: { x: number; y: number; width: number; height: number };
  handle: string;
} | null = null;
const toolbarPosition = computed(() => {
  const r = selection.value;
  if (!r) return { left: "0px", top: "0px" };
  const w = Math.min(toolbarSize.value.width, viewport.value.width - 16),
    h = toolbarSize.value.height;
  let x = Math.max(
    8,
    Math.min(r.x + r.width - w, viewport.value.width - w - 8),
  );
  let y = r.y + r.height + 12;
  if (y + h > viewport.value.height - 8) y = r.y - h - 12;
  if (y < 8) {
    y = Math.max(8, viewport.value.height - h - 8);
    if (r.x + r.width + w + 12 < viewport.value.width) x = r.x + r.width + 12;
  }
  return { left: `${x}px`, top: `${y}px`, maxWidth: `${w}px` };
});
const pixelSelection = computed(() => {
  const r = selection.value;
  return r
    ? {
        x: Math.round((r.x - origin.x) / scale),
        y: Math.round((r.y - origin.y) / scale),
        width: Math.round(r.width / scale),
        height: Math.round(r.height / scale),
      }
    : null;
});
const handles = computed(() =>
  selection.value ? ["nw", "n", "ne", "e", "se", "s", "sw", "w"] : [],
);
function textAppearance() {
  return {
    color: editingText ? String(editingText.fill()) : color.value,
    fontSize:
      (editingText
        ? editingText.fontSize() * editingText.scaleY() * scale
        : 22) + "px",
  };
}
watch(toolbar, (element) => {
  toolbarObserver?.disconnect();
  if (!element) return;
  toolbarObserver = new ResizeObserver((entries) => {
    const rect = entries[0].borderBoxSize?.[0];
    if (rect)
      toolbarSize.value = { width: rect.inlineSize, height: rect.blockSize };
  });
  toolbarObserver.observe(element);
});
function point(e: PointerEvent) {
  return {
    x: Math.max(origin.x, Math.min(origin.x + imageWidth * scale, e.clientX)),
    y: Math.max(origin.y, Math.min(origin.y + imageHeight * scale, e.clientY)),
  };
}
function local(p: { x: number; y: number }) {
  return { x: (p.x - origin.x) / scale, y: (p.y - origin.y) / scale };
}
function commit() {
  history.slice(historyIndex + 1).forEach((g) => g.destroy());
  history = history.slice(0, historyIndex + 1);
  history.push(annotations.clone());
  historyIndex = history.length - 1;
  undoCount.value = historyIndex;
  redoCount.value = 0;
}
function restore(delta: number) {
  if (historyIndex + delta < 0 || historyIndex + delta >= history.length)
    return;
  historyIndex += delta;
  transform.nodes([]);
  objectSelected.value = false;
  annotations.destroy();
  annotations = history[historyIndex].clone();
  layer.add(annotations);
  transform.moveToTop();
  annotations.clip(pixelSelection.value || undefined);
  undoCount.value = historyIndex;
  redoCount.value = history.length - historyIndex - 1;
  layer.batchDraw();
}
function setTool(id: string) {
  finishText();
  tool.value = tool.value === id ? "select" : id;
  transform.nodes([]);
  objectSelected.value = false;
}
function selectObject(node: Konva.Node | null) {
  transform.nodes(node ? [node] : []);
  objectSelected.value = !!node;
  layer.draw();
}
function hitObject(p: { x: number; y: number }) {
  const q = local(p);
  return [...annotations.getChildren()].reverse().find((n) => {
    if (n.attrs.eraser || !n.visible()) return false;
    const r = n.getClientRect({ relativeTo: annotations });
    return (
      q.x >= r.x - 4 / scale &&
      q.y >= r.y - 4 / scale &&
      q.x <= r.x + r.width + 4 / scale &&
      q.y <= r.y + r.height + 4 / scale
    );
  });
}
function deleteObject() {
  transform.nodes().forEach((n) => n.destroy());
  selectObject(null);
  commit();
}
function editTextAt(e: MouseEvent) {
  if (
    (e.target as HTMLElement).closest(".floating-tools,.overlay-text") ||
    !annotations
  )
    return;
  const node = hitObject({ x: e.clientX, y: e.clientY });
  if (!(node instanceof Konva.Text)) return;
  editingText = node;
  text.value = node.text();
  textPosition.value = {
    x: origin.x + node.x() * scale,
    y: origin.y + node.y() * scale,
  };
  node.hide();
  selectObject(null);
  setTimeout(() => textInput.value?.focus(), 0);
}
function selectAll() {
  selection.value = {
    x: origin.x,
    y: origin.y,
    width: imageWidth * scale,
    height: imageHeight * scale,
  };
  annotations.clip(pixelSelection.value!);
}
function begin(e: PointerEvent) {
  if (!ready.value || busy.value || e.button !== 0) return;
  const target = e.target as HTMLElement;
  if (
    target.closest(
      ".floating-tools,.overlay-text,.overlay-error,.overlay-controls,.overlay-cancel",
    )
  )
    return;
  const p = point(e);
  cursor.value = p;
  if (textPosition.value) {
    finishText();
    return;
  }
  if (transform.isTransforming() || transforming) return;
  // Konva owns transformer handles; screen selection must not consume that drag.
  stage.setPointersPositions(e);
  const hit = stage.getIntersection(p);
  if (hit && hit.getParent() === transform && hit.hasName("_anchor")) return;
  if (selection.value && target.dataset.handle) {
    moveStart = {
      ...p,
      selection: { ...selection.value },
      handle: target.dataset.handle,
    };
    dragging.value = true;
    return;
  }
  if (selection.value && (tool.value === "select" || tool.value === "text")) {
    const node = hitObject(p);
    if (node) {
      selectObject(node);
      objectDrag = { node, start: p, position: node.position() };
      return;
    }
  }
  if (selection.value && tool.value === "select") {
    const r = selection.value;
    selectObject(null);
    if (
      p.x >= r.x &&
      p.y >= r.y &&
      p.x <= r.x + r.width &&
      p.y <= r.y + r.height
    ) {
      moveStart = { ...p, selection: { ...r }, handle: "move" };
      dragging.value = true;
      return;
    }
  }
  if (selection.value && tool.value !== "select") {
    const r = selection.value;
    if (p.x < r.x || p.y < r.y || p.x > r.x + r.width || p.y > r.y + r.height)
      return;
    anchor = local(p);
    selectObject(null);
    if (tool.value === "eraser") {
      shape = new Konva.Line({
        points: [anchor.x, anchor.y, anchor.x + 0.01, anchor.y],
        stroke: "#000",
        strokeWidth: eraseSize.value / scale,
        lineCap: "round",
        lineJoin: "round",
        globalCompositeOperation: "destination-out",
        eraser: true,
        listening: false,
      });
      annotations.add(shape);
      return;
    }
    if (tool.value === "text") {
      text.value = "";
      textPosition.value = p;
      setTimeout(() => textInput.value?.focus(), 0);
      return;
    }
    const attrs = {
      x: anchor.x,
      y: anchor.y,
      stroke: color.value,
      strokeWidth: stroke.value / scale,
      name: "annotation",
    };
    if (tool.value === "ellipse") shape = new Konva.Ellipse(attrs);
    else if (tool.value === "arrow")
      shape = new Konva.Arrow({
        ...attrs,
        x: 0,
        y: 0,
        points: [anchor.x, anchor.y, anchor.x, anchor.y],
        fill: color.value,
        pointerLength: 12 / scale,
        pointerWidth: 10 / scale,
      });
    else if (tool.value === "pen")
      shape = new Konva.Line({
        ...attrs,
        x: 0,
        y: 0,
        points: [anchor.x, anchor.y],
        lineCap: "round",
        lineJoin: "round",
      });
    else
      shape = new Konva.Rect({
        ...attrs,
        fill: tool.value === "mosaic" ? "#ffffff40" : undefined,
      });
    annotations.add(shape);
    return;
  }
  if (tool.value === "select" && !target.closest(".selection-box")) {
    transform.nodes([]);
    anchor = p;
    identify(p);
    clickedRegion = hoverRegion.value;
    selection.value = null;
    dragging.value = true;
  }
}
function move(e: PointerEvent) {
  const p = point(e);
  cursor.value = p;
  if (!ready.value) return;
  if (!selection.value && !dragging.value) identify(p);
  const r = selection.value;
  canvasCursor.value =
    r &&
    tool.value === "select" &&
    p.x >= r.x &&
    p.y >= r.y &&
    p.x <= r.x + r.width &&
    p.y <= r.y + r.height
      ? "move"
      : "crosshair";
  if (transforming) return;
  if (objectDrag) {
    objectDrag.node.position({
      x: objectDrag.position.x + (p.x - objectDrag.start.x) / scale,
      y: objectDrag.position.y + (p.y - objectDrag.start.y) / scale,
    });
    layer.batchDraw();
    return;
  }
  if (moveStart) {
    const s = moveStart.selection,
      dx = p.x - moveStart.x,
      dy = p.y - moveStart.y,
      h = moveStart.handle;
    if (h === "move") {
      selection.value = {
        ...s,
        x: Math.max(
          origin.x,
          Math.min(origin.x + imageWidth * scale - s.width, s.x + dx),
        ),
        y: Math.max(
          origin.y,
          Math.min(origin.y + imageHeight * scale - s.height, s.y + dy),
        ),
      };
    } else {
      let x1 = s.x,
        y1 = s.y,
        x2 = s.x + s.width,
        y2 = s.y + s.height;
      if (h.includes("w")) x1 = Math.min(x2 - 3, p.x);
      if (h.includes("e")) x2 = Math.max(x1 + 3, p.x);
      if (h.includes("n")) y1 = Math.min(y2 - 3, p.y);
      if (h.includes("s")) y2 = Math.max(y1 + 3, p.y);
      selection.value = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
    }
    annotations.clip(pixelSelection.value!);
    return;
  }
  if (shape) {
    const r = selection.value!;
    const q = local({
      x: Math.max(r.x, Math.min(r.x + r.width, p.x)),
      y: Math.max(r.y, Math.min(r.y + r.height, p.y)),
    });
    const x = Math.min(anchor.x, q.x),
      y = Math.min(anchor.y, q.y),
      w = Math.abs(q.x - anchor.x),
      h = Math.abs(q.y - anchor.y);
    if (shape instanceof Konva.Arrow)
      shape.points([anchor.x, anchor.y, q.x, q.y]);
    else if (shape instanceof Konva.Line)
      shape.points([...shape.points(), q.x, q.y]);
    else if (shape instanceof Konva.Ellipse) {
      shape.position({ x: x + w / 2, y: y + h / 2 });
      shape.radius({ x: w / 2, y: h / 2 });
    } else {
      shape.position({ x, y });
      shape.size({ width: w, height: h });
    }
    return;
  }
  if (dragging.value)
    selection.value = {
      x: Math.min(anchor.x, p.x),
      y: Math.min(anchor.y, p.y),
      width: Math.abs(p.x - anchor.x),
      height: Math.abs(p.y - anchor.y),
    };
}
function end() {
  if (objectDrag) {
    const changed =
      objectDrag.node.x() !== objectDrag.position.x ||
      objectDrag.node.y() !== objectDrag.position.y;
    objectDrag = null;
    if (changed) commit();
    return;
  }
  if (transforming) return;
  if (moveStart) {
    moveStart = null;
    dragging.value = false;
    return;
  }
  if (shape) {
    if (tool.value === "mosaic") pixelate(shape as Konva.Rect);
    else commit();
    shape = null;
  }
  if (dragging.value) {
    dragging.value = false;
    if (
      !selection.value ||
      selection.value.width < 3 ||
      selection.value.height < 3
    ) {
      selection.value = clickedRegion
        ? screenRegion(clickedRegion)
        : {
            x: origin.x,
            y: origin.y,
            width: imageWidth * scale,
            height: imageHeight * scale,
          };
    }
    annotations.destroyChildren();
    annotations.clip(pixelSelection.value!);
    history.forEach((g) => g.destroy());
    history = [];
    historyIndex = -1;
    commit();
  }
}
function pixelate(rect: Konva.Rect) {
  const x = Math.floor(rect.x()),
    y = Math.floor(rect.y()),
    w = Math.max(1, Math.ceil(rect.width())),
    h = Math.max(1, Math.ceil(rect.height()));
  rect.destroy();
  const tiny = document.createElement("canvas");
  tiny.width = Math.max(1, Math.ceil(w / (12 / scale)));
  tiny.height = Math.max(1, Math.ceil(h / (12 / scale)));
  tiny
    .getContext("2d")!
    .drawImage(image, x, y, w, h, 0, 0, tiny.width, tiny.height);
  const full = document.createElement("canvas");
  full.width = w;
  full.height = h;
  const ctx = full.getContext("2d")!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tiny, 0, 0, w, h);
  annotations.add(
    new Konva.Image({
      x,
      y,
      width: w,
      height: h,
      image: full,
      name: "annotation",
    }),
  );
  commit();
}
function finishText() {
  if (!textPosition.value) return;
  if (text.value.trim()) {
    const p = local(textPosition.value);
    const node =
      editingText ||
      new Konva.Text({
        ...p,
        text: text.value,
        fontFamily: "Noto Sans CJK SC, sans-serif",
        fontSize: 22 / scale,
        fill: color.value,
        name: "annotation",
      });
    node.text(text.value);
    node.show();
    if (!editingText) annotations.add(node);
    tool.value = "select";
    selectObject(node);
    commit();
  } else if (editingText) editingText.show();
  editingText = null;
  textPosition.value = null;
  text.value = "";
}
async function finish(action: "copy" | "save" | "pin") {
  if (busy.value || !pixelSelection.value) return;
  finishText();
  busy.value = true;
  error.value = "";
  try {
    transform.nodes([]);
    layer.draw();
    const pixels = pixelSelection.value!;
    // Render detached original-pixel nodes so display scaling never resamples exports.
    const output = new Konva.Group();
    output.add(background.clone());
    // Eraser composites only the annotation layer, never the original screenshot.
    const ink = annotations.clone();
    ink.cache({
      x: 0,
      y: 0,
      width: imageWidth,
      height: imageHeight,
      pixelRatio: 1,
    });
    output.add(ink);
    const data = output.toDataURL({ ...pixels, pixelRatio: 1 });
    output.destroy();
    const saved = await rpc<Shot>("import", {
      data,
      ...(props.shot ? { parent_id: props.shot.id } : {}),
    });
    if (action === "copy") await rpc("clipboard", { id: saved.id });
    if (action === "save") {
      if (native) await invoke("save_image", { id: saved.id });
      else {
        const a = document.createElement("a");
        a.href = data;
        a.download = "linger-capture.png";
        a.click();
      }
    }
    if (action === "pin") {
      if (native)
        await invoke("pin_image", {
          id: saved.id,
          width: saved.width,
          height: saved.height,
        });
      else
        window.open(`?pin=${saved.id}`, "_blank", "popup,width=640,height=480");
    }
    emit("saved", saved);
    emit("close");
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e);
  } finally {
    busy.value = false;
  }
}
function key(e: KeyboardEvent) {
  if (!ready.value || busy.value || e.isComposing) return;
  if ((e.target as HTMLElement).matches("input")) {
    if (e.key === "Enter") {
      e.preventDefault();
      finishText();
    }
    if (e.key === "Escape") {
      editingText?.show();
      editingText = null;
      textPosition.value = null;
      layer.batchDraw();
    }
    return;
  }
  if (e.key === "Escape") {
    e.preventDefault();
    if (objectSelected.value) {
      selectObject(null);
      return;
    }
    emit("close");
  }
  if (e.key === "Enter") {
    e.preventDefault();
    if (selection.value) finish("copy");
    else if (hoverRegion.value) {
      selection.value = screenRegion(hoverRegion.value);
      annotations.clip(pixelSelection.value!);
    } else selectAll();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "a") {
    e.preventDefault();
    selectAll();
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
    e.preventDefault();
    finish("copy");
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    finish("save");
  }
  if (e.key === "F2") {
    e.preventDefault();
    finish("pin");
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    restore(e.shiftKey ? 1 : -1);
  }
  if (
    selection.value &&
    ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
  ) {
    e.preventDefault();
    const step = e.shiftKey ? 10 : 1,
      r = selection.value;
    const dx =
        e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0,
      dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
    if (objectSelected.value) {
      transform
        .nodes()
        .forEach((n) => n.move({ x: dx / scale, y: dy / scale }));
      commit();
      return;
    }
    selection.value = {
      ...r,
      x: Math.max(
        origin.x,
        Math.min(origin.x + imageWidth * scale - r.width, r.x + dx),
      ),
      y: Math.max(
        origin.y,
        Math.min(origin.y + imageHeight * scale - r.height, r.y + dy),
      ),
    };
    annotations.clip(pixelSelection.value!);
  }
  if (e.key === "Delete" || e.key === "Backspace") {
    if (objectSelected.value) {
      e.preventDefault();
      deleteObject();
    }
  }
}
function resize() {
  if (!stage) return;
  const previous = pixelSelection.value;
  viewport.value = { width: innerWidth, height: innerHeight };
  stage.size(viewport.value);
  if (imageWidth) {
    scale = Math.min(innerWidth / imageWidth, innerHeight / imageHeight);
    origin = {
      x: (innerWidth - imageWidth * scale) / 2,
      y: (innerHeight - imageHeight * scale) / 2,
    };
    stage.scale({ x: scale, y: scale });
    stage.position(origin);
    if (previous)
      selection.value = {
        x: origin.x + previous.x * scale,
        y: origin.y + previous.y * scale,
        width: previous.width * scale,
        height: previous.height * scale,
      };
  }
}
onMounted(() => {
  stage = new Konva.Stage({
    container: host.value!,
    width: innerWidth,
    height: innerHeight,
  });
  layer = new Konva.Layer();
  stage.add(layer);
  image = new Image();
  image.onload = async () => {
    imageWidth = image.naturalWidth;
    imageHeight = image.naturalHeight;
    background = new Konva.Image({
      image,
      width: imageWidth,
      height: imageHeight,
      listening: false,
    });
    annotations = new Konva.Group();
    transform = new Konva.Transformer({
      rotateEnabled: false,
      enabledAnchors: [
        "top-left",
        "top-center",
        "top-right",
        "middle-left",
        "middle-right",
        "bottom-left",
        "bottom-center",
        "bottom-right",
      ],
      anchorSize: 11,
      anchorFill: "#fff",
      anchorStroke: "#46baad",
      borderDash: [4, 3],
      padding: 8,
      anchorStyleFunc: (anchor) => anchor.hitStrokeWidth(4),
      flipEnabled: false,
      boundBoxFunc: (oldBox, newBox) =>
        Math.abs(newBox.width) < 12 || Math.abs(newBox.height) < 12
          ? oldBox
          : newBox,
      borderStroke: "#58bcae",
    });
    transform.on("transformstart", () => {
      transforming = true;
      objectDrag = null;
    });
    transform.on("transformend", () => {
      transforming = false;
      commit();
    });
    const baseLayer = new Konva.Layer({ listening: false });
    stage.add(baseLayer);
    baseLayer.moveToBottom();
    baseLayer.add(background);
    layer.add(annotations, transform);
    resize();
    commit();
    if (new URLSearchParams(location.search).get("whole") === "1") selectAll();
    ready.value = true;
    cursor.value = { ...origin };
    if (native) await invoke("overlay_ready");
    if (native) {
      const stop = await listen("pin-selection", () => {
        if (selection.value && !busy.value) finish("pin");
      });
      if (disposed) stop();
      else unlistenPin = stop;
    }
  };
  image.src = props.src;
  image.onerror = () => {
    error.value = "图片加载失败，请关闭后重新打开。";
    if (native) invoke("overlay_ready");
  };
  observer = new ResizeObserver(resize);
  observer.observe(host.value!);
  window.addEventListener("keydown", key);
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
});
onBeforeUnmount(() => {
  disposed = true;
  unlistenPin?.();
  observer.disconnect();
  toolbarObserver?.disconnect();
  stage.destroy();
  history.forEach((g) => g.destroy());
  window.removeEventListener("keydown", key);
  window.removeEventListener("pointermove", move);
  window.removeEventListener("pointerup", end);
});
</script>
<template>
  <div
    class="capture-overlay"
    :class="{ 'annotation-mode': tool !== 'select' }"
    :style="{ cursor: canvasCursor }"
    @pointerdown="begin"
    @dblclick="editTextAt"
    @contextmenu.prevent="emit('close')"
    @wheel="cycleRegion"
  >
    <div
      ref="host"
      class="capture-pixels"
      role="img"
      aria-label="冻结的屏幕画面"
    ></div>
    <div v-if="!selection && !hoverBox" class="capture-dim"></div>
    <div
      v-if="!selection && hoverBox && !dragging"
      class="hover-region"
      :style="{
        left: hoverBox.x + 'px',
        top: hoverBox.y + 'px',
        width: hoverBox.width + 'px',
        height: hoverBox.height + 'px',
      }"
    >
      <span :style="{ top: hoverBox.y < 36 ? '6px' : '-29px' }"
        >{{ Math.round(hoverRegion!.width * imageWidth) }} ×
        {{ Math.round(hoverRegion!.height * imageHeight) }} ·
        {{ hoverIndex + 1 }}/{{ hoverRegions.length }}</span
      >
    </div>
    <p
      v-if="!selection && ready && (detecting || detectionError)"
      class="detection-help"
    >
      {{ detecting ? "正在识别容器区域…" : detectionError }}
    </p>
    <template v-if="selection">
      <div
        class="selection-box"
        :class="{
          drawing: tool !== 'select',
          'object-selected': objectSelected,
        }"
        :style="{
          left: selection.x + 'px',
          top: selection.y + 'px',
          width: selection.width + 'px',
          height: selection.height + 'px',
        }"
      >
        <span
          class="selection-size"
          :style="{ top: selection.y < 32 ? '6px' : '-29px' }"
          >{{ pixelSelection?.width }} × {{ pixelSelection?.height }}</span
        >
        <button
          v-for="handle in handles"
          :key="handle"
          class="selection-handle"
          :class="handle"
          :data-handle="handle"
          :aria-label="`调整选区 ${handle}`"
          tabindex="-1"
        ></button>
      </div>
      <div
        v-if="!dragging"
        ref="toolbar"
        class="floating-tools"
        :style="toolbarPosition"
      >
        <div v-if="tool !== 'select'" class="floating-options">
          <label v-if="tool === 'eraser'"
            >橡皮大小<input
              v-model.number="eraseSize"
              type="range"
              min="8"
              max="100"
              aria-label="橡皮大小"
          /></label>
          <template v-else>
            <button
              v-for="c in colors"
              :key="c"
              :aria-label="`颜色 ${c}`"
              :aria-pressed="color === c"
              :style="{ background: c }"
              :class="{ chosen: color === c }"
              @click="color = c"
            ></button
            ><span></span
            ><label
              >粗细<input
                v-model.number="stroke"
                type="range"
                min="1"
                max="10"
                aria-label="标注粗细"
            /></label>
          </template>
        </div>
        <div
          class="floating-actions"
          role="toolbar"
          aria-label="截图标注与完成操作"
        >
          <IconButton
            :icon="MousePointer2"
            label="调整选区"
            :active="tool === 'select'"
            @click="setTool('select')"
          />
          <IconButton :icon="Scan" label="选取全屏 Ctrl A" @click="selectAll" />
          <IconButton
            v-for="item in tools"
            :key="item.id"
            :icon="item.icon"
            :label="item.label"
            :active="tool === item.id"
            @click="setTool(item.id)"
          />
          <i></i
          ><IconButton
            :icon="Undo2"
            label="撤销"
            :disabled="undoCount === 0"
            @click="restore(-1)"
          /><IconButton
            :icon="Redo2"
            label="重做"
            :disabled="redoCount === 0"
            @click="restore(1)"
          />
          <IconButton
            v-if="objectSelected"
            :icon="Trash2"
            label="删除标注 Delete"
            @click="deleteObject"
          />
          <i></i
          ><IconButton
            :icon="Pin"
            label="贴图 F2"
            :disabled="busy"
            @click="finish('pin')"
          /><IconButton
            :icon="Download"
            label="保存 Ctrl S"
            :disabled="busy"
            @click="finish('save')"
          /><IconButton
            :icon="X"
            label="取消 Esc"
            :disabled="busy"
            @click="emit('close')"
          /><IconButton
            :icon="Check"
            label="复制并完成 Enter"
            :disabled="busy"
            class="complete-capture"
            @click="finish('copy')"
          />
        </div>
      </div>
    </template>
    <input
      v-if="textPosition"
      ref="textInput"
      v-model="text"
      class="overlay-text"
      name="annotation"
      autocomplete="off"
      aria-label="标注文字"
      :style="{
        left: textPosition.x + 'px',
        top: textPosition.y + 'px',
        ...textAppearance(),
      }"
      @blur="finishText"
    />
    <div
      v-if="tool === 'eraser' && selection"
      class="eraser-cursor"
      :style="{
        left: cursor.x + 'px',
        top: cursor.y + 'px',
        width: eraseSize + 'px',
        height: eraseSize + 'px',
      }"
    ></div>
    <div
      v-if="!selection && ready"
      class="capture-crosshair"
      :style="{
        left: cursor.x + 18 + 'px',
        top: Math.min(cursor.y + 22, viewport.height - 34) + 'px',
      }"
    >
      {{ Math.round((cursor.x - origin.x) / scale) }},
      {{ Math.round((cursor.y - origin.y) / scale) }}
    </div>
    <div v-if="error" class="overlay-error" role="alert">
      {{ error }}<button @click="error = ''">关闭</button>
    </div>
    <button
      v-if="!selection"
      class="overlay-cancel"
      aria-label="取消截图"
      @click="emit('close')"
    >
      <X :size="20" aria-hidden="true" />
    </button>
  </div>
</template>
