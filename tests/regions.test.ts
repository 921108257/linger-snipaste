import { describe, it, expect } from "vitest";
import { regionsAt } from "../src/lib/regions";
describe("container hit testing", () => {
  const outer = { x: 0.1, y: 0.1, width: 0.8, height: 0.8 };
  const inner = { x: 0.2, y: 0.2, width: 0.3, height: 0.4 };
  it("prefers the inner container and retains the enclosing surface and image", () => {
    expect(regionsAt([outer, inner], 0.3, 0.3)).toEqual([
      inner,
      outer,
      { x: 0, y: 0, width: 1, height: 1 },
    ]);
    expect(regionsAt([outer, inner], 0.8, 0.8)).toHaveLength(2);
  });
  it("ignores malformed and offscreen boxes", () => {
    expect(
      regionsAt(
        [
          { ...inner, x: NaN },
          { ...inner, width: 2 },
        ],
        0.3,
        0.3,
      ),
    ).toHaveLength(1);
    expect(regionsAt([outer, inner], -1, 0.3)).toEqual([]);
  });
});
