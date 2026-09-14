import { createCanvas, Image } from "@napi-rs/canvas";
import { vi } from "vitest";

// Real rasterization behind jsdom's canvas, without driving a browser or desktop.
const surfaces = new WeakMap<
  HTMLCanvasElement,
  ReturnType<typeof createCanvas>
>();
function surface(element: HTMLCanvasElement) {
  let canvas = surfaces.get(element);
  if (!canvas) {
    canvas = createCanvas(element.width || 1, element.height || 1);
    surfaces.set(element, canvas);
  }
  if (canvas.width !== (element.width || 1)) canvas.width = element.width || 1;
  if (canvas.height !== (element.height || 1))
    canvas.height = element.height || 1;
  return canvas;
}
HTMLCanvasElement.prototype.getContext = function () {
  const context = surface(this).getContext("2d");
  const element = this;
  return new Proxy(context, {
    get(target, key) {
      surface(element);
      if (key === "drawImage")
        return (source: unknown, ...args: number[]) => {
          const image =
            source instanceof HTMLCanvasElement ? surface(source) : source;
          return (target.drawImage as Function).call(target, image, ...args);
        };
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
    set(target, key, value) {
      surface(element);
      return Reflect.set(target, key, value, target);
    },
  }) as any;
};
HTMLCanvasElement.prototype.toDataURL = function () {
  return surface(this).toDataURL("image/png");
};
vi.stubGlobal("Image", Image);
vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    disconnect() {}
  },
);
Object.defineProperty(window, "innerWidth", { value: 1200, writable: true });
Object.defineProperty(window, "innerHeight", { value: 760, writable: true });
