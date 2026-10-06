// Bundles src/main.tsx -> dist/ with esbuild. (Vite/Tailwind/Monaco/Framer Motion could not be installed in the
// dev sandbox - see README "Stack deviations".)
import { build, context } from "esbuild";
import { cpSync, mkdirSync, rmSync } from "node:fs";

const watch = process.argv.includes("--watch");
rmSync("dist", { recursive: true, force: true });
mkdirSync("dist", { recursive: true });
cpSync("public", "dist", { recursive: true });
const opts = {
  entryPoints: ["src/main.tsx", "src/styles.css"],
  outdir: "dist/assets", bundle: true, minify: !watch, sourcemap: true, target: "es2022",
  jsx: "automatic", loader: { ".svg": "text" }, define: { "process.env.NODE_ENV": watch ? '"development"' : '"production"' },
  logLevel: "info",
};
if (watch) { const c = await context(opts); await c.watch(); } else { await build(opts); }
