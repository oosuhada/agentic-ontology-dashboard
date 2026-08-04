import { copyFile, mkdir, writeFile } from "node:fs/promises";

const distRoot = new URL("../dist/", import.meta.url);
const indexFile = new URL("index.html", distRoot);
const teamShareDirectory = new URL("team-share/", distRoot);

await mkdir(teamShareDirectory, { recursive: true });
await copyFile(indexFile, new URL("index.html", teamShareDirectory));
await copyFile(indexFile, new URL("404.html", distRoot));
await writeFile(new URL(".nojekyll", distRoot), "", "utf8");

console.log("Prepared GitHub Pages routes: /team-share/ and /404.html");
