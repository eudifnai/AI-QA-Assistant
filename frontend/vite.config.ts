import vue from "@vitejs/plugin-vue";
import { transformWithEsbuild, type Plugin } from "vite";
import { defineConfig } from "vitest/config";

function commonJsTypeScriptPlugin(): Plugin {
  return {
    name: "transform-commonjs-typescript",
    enforce: "pre",
    async transform(code, id) {
      if (!id.endsWith(".cts")) {
        return null;
      }
      const result = await transformWithEsbuild(code, id, { loader: "ts", format: "esm" });
      return { code: result.code, map: JSON.stringify(result.map) };
    },
  };
}

export default defineConfig({
  plugins: [commonJsTypeScriptPlugin(), vue()],
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    restoreMocks: true,
  },
});
