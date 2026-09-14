export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Coordinates are normalized against the captured image, never desktop CSS
// pixels: cropped portal images, letterboxing and HiDPI share the same mapping.
export function regionsAt(regions: Region[], x: number, y: number): Region[] {
  if (x < 0 || y < 0 || x > 1 || y > 1) return [];
  const matches = regions
    .filter(
      (r) =>
        [r.x, r.y, r.width, r.height].every(Number.isFinite) &&
        r.x >= 0 &&
        r.y >= 0 &&
        r.width > 0 &&
        r.height > 0 &&
        r.x + r.width <= 1.001 &&
        r.y + r.height <= 1.001 &&
        x >= r.x &&
        x < r.x + r.width &&
        y >= r.y &&
        y < r.y + r.height,
    )
    .sort((a, b) => a.width * a.height - b.width * b.height);
  return [...matches, { x: 0, y: 0, width: 1, height: 1 }];
}
