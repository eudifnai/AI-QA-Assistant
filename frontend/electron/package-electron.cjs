import("../.electron/package-runtime.cjs")
  .then(({ packageElectron }) => packageElectron(process.cwd()))
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
