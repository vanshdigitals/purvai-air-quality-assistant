import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const tempDbPath = path.join(os.tmpdir(), `purvai-e2e-${process.pid}-${Date.now()}.db`);
const venvPython =
  process.platform === "win32"
    ? path.resolve("..", ".venv", "Scripts", "python.exe")
    : path.resolve("..", ".venv", "bin", "python");
const pythonExec = fs.existsSync(venvPython) ? venvPython : "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "on-first-retry",
  },
  webServer: {
    command: `"${pythonExec}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
    cwd: "../backend",
    url: "http://127.0.0.1:8000/api/v1/health",
    reuseExistingServer: false,
    timeout: 60000,
    env: {
      ...process.env,
      PURVAI_MODE: "local",
      PURVAI_FAKE_PROVIDERS: "true",
      DATABASE_PATH: tempDbPath,
      RATE_LIMIT_PER_MINUTE: "10000",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
