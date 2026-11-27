/* global console, process */
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const DIST_DIR = path.resolve(import.meta.dirname, "..", "dist");
const ASSETS_DIR = path.join(DIST_DIR, "assets");
const LIMIT_BYTES = 250 * 1024;

const indexHtml = fs.readFileSync(path.join(DIST_DIR, "index.html"), "utf-8");
const entryMatch = indexHtml.match(/src="\/assets\/([^"]+\.js)"/);
if (!entryMatch) {
  console.error("Could not find entry JS bundle in dist/index.html");
  process.exit(1);
}

const files = fs.readdirSync(ASSETS_DIR);
const todayChunk = files.find((f) => /^TodayPage-.*\.js$/.test(f));
const forecastChunk = files.find((f) => /^ForecastSection-.*\.js$/.test(f));

const targetChunks = [entryMatch[1], todayChunk, forecastChunk].filter(Boolean);
let totalGzipBytes = 0;

for (const name of targetChunks) {
  const raw = fs.readFileSync(path.join(ASSETS_DIR, name));
  const gz = zlib.gzipSync(raw);
  totalGzipBytes += gz.length;
  console.log(`${name}: ${(gz.length / 1024).toFixed(2)} KB gzip`);
}

console.log(
  `First-visit /today JS total: ${(totalGzipBytes / 1024).toFixed(2)} KB gzip (limit 250.00 KB)`
);

if (totalGzipBytes > LIMIT_BYTES) {
  console.error(`Bundle size ${totalGzipBytes} bytes exceeds ${LIMIT_BYTES} bytes`);
  process.exit(1);
}
