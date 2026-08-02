import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const distRoot = resolve(process.cwd(), "dist");
const indexPath = resolve(distRoot, "index.html");
const budgetKb = Number(process.env.INITIAL_BUNDLE_BUDGET_KB ?? "300");

if (!Number.isFinite(budgetKb) || budgetKb <= 0) {
  throw new Error("INITIAL_BUNDLE_BUDGET_KB must be a positive number.");
}

const html = await readFile(indexPath, "utf8");
const assetPattern = /<(?:script|link)\b[^>]*(?:src|href)="([^"]+\.js)"[^>]*>/g;
const assetPaths = [...html.matchAll(assetPattern)]
  .map((match) => match[1])
  .filter((value, index, values) => values.indexOf(value) === index);

if (assetPaths.length === 0) {
  throw new Error(`No initial JavaScript assets were found in ${indexPath}.`);
}

const assets = await Promise.all(assetPaths.map(async (assetPath) => {
  const normalizedPath = assetPath.replace(/^\//, "");
  const filePath = resolve(distRoot, normalizedPath);
  const file = await stat(filePath);
  return { assetPath, bytes: file.size };
}));

const totalBytes = assets.reduce((sum, asset) => sum + asset.bytes, 0);
const totalKb = totalBytes / 1024;
const detail = assets
  .map((asset) => `${asset.assetPath} ${(asset.bytes / 1024).toFixed(2)} KiB`)
  .join(", ");

console.log(`Initial JavaScript bundle: ${totalKb.toFixed(2)} KiB / ${budgetKb.toFixed(0)} KiB budget`);
console.log(`Initial assets: ${detail}`);

if (totalKb > budgetKb) {
  throw new Error(
    `Initial JavaScript bundle exceeded the ${budgetKb.toFixed(0)} KiB budget by ${(totalKb - budgetKb).toFixed(2)} KiB.`,
  );
}
