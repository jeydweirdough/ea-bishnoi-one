// Renders the Executive Admin mark into the PNG sizes the PWA manifest needs.
// Run: node scripts/make-icons.mjs
import sharp from "sharp";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const out = new URL("../public/icons/", import.meta.url);
await mkdir(out, { recursive: true });

// Standard icon: ink tile with the accent ring (same as <Mark/>).
const tile = (rx) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="${rx}" fill="#111111"/>
  <circle cx="16" cy="16" r="7" fill="none" stroke="#A6C23F" stroke-width="3"/>
</svg>`;

// Maskable: full-bleed ink, ring kept inside the 80% safe zone.
const maskable = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" fill="#111111"/>
  <circle cx="16" cy="16" r="5.6" fill="none" stroke="#A6C23F" stroke-width="2.4"/>
</svg>`;

await writeFile(new URL("icon.svg", out), tile(8));
const jobs = [
  ["icon-192.png", tile(8), 192],
  ["icon-512.png", tile(8), 512],
  ["icon-maskable-512.png", maskable, 512],
  ["apple-touch-icon.png", tile(0), 180],
];
for (const [name, svg, size] of jobs) {
  await sharp(Buffer.from(svg)).resize(size, size).png().toFile(fileURLToPath(new URL(name, out)));
}
console.log("icons written");
