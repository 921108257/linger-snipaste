import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import { nextTick } from "vue";
import Konva from "konva";
import { createCanvas, loadImage } from "@napi-rs/canvas";
import CaptureOverlay from "../src/components/CaptureOverlay.vue";

const { rpc } = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("../src/lib/api", () => ({ native: false, rpc }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let wrapper: VueWrapper;
let stage: Konva.Stage;
let source: string;
function pointer(target: EventTarget, type: string, x: number, y: number) {
  target.dispatchEvent(
    new MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true }),
  );
}
async function drag(
  x: number,
  y: number,
  endX: number,
  endY: number,
  target?: Element,
) {
  pointer(
    target || wrapper.get(".capture-pixels canvas").element,
    "pointerdown",
    x,
    y,
  );
  pointer(window, "pointermove", endX, endY);
  pointer(window, "pointerup", endX, endY);
  stage.draw();
  await nextTick();
}
async function clickTool(label: string) {
  await wrapper.get(`[aria-label="${label}"]`).trigger("click");
  stage.draw();
}
function box() {
  const style = (wrapper.get(".selection-box").element as HTMLElement).style;
  return [style.left, style.top, style.width, style.height].map(parseFloat);
}
async function addText() {
  await clickTool("文字");
  await drag(230, 220, 230, 220);
  await wrapper.get('input[name="annotation"]').setValue("Hello");
  if (wrapper.find('input[name="annotation"]').exists())
    await wrapper
      .get('input[name="annotation"]')
      .trigger("keydown", { key: "Enter" });
  stage.draw();
  await nextTick();
  return stage.find("Text")[0] as Konva.Text;
}
async function exported() {
  rpc.mockResolvedValue({ id: "test", width: 700, height: 400 });
  await clickTool("复制并完成 Enter");
  await vi.waitFor(() =>
    expect(rpc).toHaveBeenCalledWith("import", expect.anything()),
  );
  const data = rpc.mock.calls.find((c) => c[0] === "import")![1].data;
  const image = await loadImage(data);
  const out = createCanvas(image.width, image.height);
  out.getContext("2d").drawImage(image, 0, 0);
  return out;
}
beforeEach(async () => {
  rpc.mockReset();
  const canvas = createCanvas(1200, 760);
  const context = canvas.getContext("2d");
  context.fillStyle = "#306090";
  context.fillRect(0, 0, 1200, 760);
  source = canvas.toDataURL("image/png");
  wrapper = mount(CaptureOverlay, {
    props: { src: source },
    attachTo: document.body,
  });
  await vi.waitFor(() =>
    expect(wrapper.find(".capture-crosshair").exists()).toBe(true),
  );
  stage = Konva.stages[Konva.stages.length - 1];
  await drag(100, 100, 800, 500);
});
afterEach(() => {
  wrapper.unmount();
  document.body.innerHTML = "";
});

describe("screenshot interaction", () => {
  it("moves the crop and resizes all eight handles", async () => {
    expect(box()).toEqual([100, 100, 700, 400]);
    await drag(400, 300, 450, 330);
    expect(box()).toEqual([150, 130, 700, 400]);
    for (const h of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
      const [x, y, w, height] = box();
      const px = h.includes("w") ? x : h.includes("e") ? x + w : x + w / 2;
      const py = h.includes("n")
        ? y
        : h.includes("s")
          ? y + height
          : y + height / 2;
      await drag(
        px,
        py,
        px + 10,
        py + 10,
        wrapper.get(`[data-handle="${h}"]`).element,
      );
      expect(box()).not.toEqual([x, y, w, height]);
    }
  });
  it("selects inserted text and supports dragging, scaling, editing and undo", async () => {
    const node = await addText();
    expect(node.text()).toBe("Hello");
    expect(wrapper.find(".object-selected").exists()).toBe(true);
    const old = node.position();
    await drag(240, 228, 290, 258);
    expect(node.position()).toEqual({ x: old.x + 50, y: old.y + 30 });
    const tr = stage.find("Transformer")[0] as Konva.Transformer;
    const handle = tr.findOne(".bottom-right")!;
    const r = handle.getClientRect();
    const p = { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    expect(stage.getIntersection(p)?.name()).toContain("bottom-right");
    const canvas = wrapper.get(".capture-pixels canvas").element;
    pointer(canvas, "mousedown", p.x, p.y);
    expect(tr.isTransforming()).toBe(true);
    pointer(window, "mousemove", p.x + 70, p.y + 30);
    pointer(window, "mouseup", p.x + 70, p.y + 30);
    stage.draw();
    expect(node.scaleX()).toBeGreaterThan(1);
    expect(node.scaleY()).toBeGreaterThan(1);
    await clickTool("撤销");
    expect((stage.find("Text")[0] as Konva.Text).scaleX()).toBe(1);
    await wrapper
      .get(".capture-pixels canvas")
      .trigger("dblclick", { clientX: 290, clientY: 258 });
    await wrapper.get('input[name="annotation"]').setValue("Edited");
    await wrapper
      .get('input[name="annotation"]')
      .trigger("keydown", { key: "Enter" });
    expect((stage.find("Text")[0] as Konva.Text).text()).toBe("Edited");
  });
  it("exports exactly the crop without dimming, handles or tools", async () => {
    const out = await exported();
    expect([out.width, out.height]).toEqual([700, 400]);
    const bytes = out
      .getContext("2d")
      .getImageData(0, 0, out.width, out.height).data;
    for (let i = 0; i < bytes.length; i += 4) {
      if (
        bytes[i] !== 48 ||
        bytes[i + 1] !== 96 ||
        bytes[i + 2] !== 144 ||
        bytes[i + 3] !== 255
      )
        throw new Error(`Changed screenshot pixel ${i / 4}`);
    }
  });
  it("erases ink without erasing the screenshot and restores it on undo", async () => {
    await clickTool("画笔");
    await drag(200, 250, 500, 250);
    await clickTool("橡皮擦");
    await drag(350, 220, 350, 280);
    const out = await exported();
    expect([...out.getContext("2d").getImageData(250, 150, 1, 1).data]).toEqual(
      [48, 96, 144, 255],
    );
    expect([...out.getContext("2d").getImageData(120, 150, 1, 1).data]).toEqual(
      [239, 83, 80, 255],
    );
    await clickTool("撤销");
    expect(stage.find("Line").filter((n) => n.attrs.eraser)).toHaveLength(0);
  });
});
