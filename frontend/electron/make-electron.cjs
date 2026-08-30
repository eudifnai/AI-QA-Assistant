import("../.electron/package-runtime.cjs")
  .then(({ makeElectron }) =>
    makeElectron(process.cwd(), process.argv.includes("--skip-package")),
  )
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
