// The two shapes of the venue's mark (docs/brand/round-1/noor-mark.svg, 200 x 200): the lamp bowl and its flame.
export const BOWL =
  "M180 70C180 131.86 144.18 182 100 182C55.82 182 20 131.86 20 70C20 61.77 20.63 53.76 21.84 46.03L46.7 43.8C46.24 48.42 46 53.16 46 58C46 106.6 70.18 146 100 146C129.82 146 154 106.6 154 58C154 49.8 153.31 41.85 152.02 34.32L175.33 32.22C178.35 44.02 180 56.74 180 70Z";
export const FLAME = "M108.65 45.37C121.77 70.24 108.72 101.33 92.21 95.97C75.7 90.6 83.42 57.78 108.65 45.37Z";

/** Places the flame's base (about 98, 96 in the mark) at (x, y), scaled by s. */
export const flameAt = (x: number, y: number, s: number) => `translate(${x} ${y}) scale(${s}) translate(-98 -96)`;
