import { spawn } from "child_process";
import path from "path";

const pythonProcess = spawn("python", ["main.py"], {
  cwd: path.join(process.cwd(), "server_py"),
  stdio: "inherit",
  env: { ...process.env, PYTHONUNBUFFERED: "1" }
});

pythonProcess.on("error", (err) => {
  console.error("Failed to start Python backend:", err);
  process.exit(1);
});

pythonProcess.on("close", (code) => {
  process.exit(code || 0);
});

process.on("SIGINT", () => pythonProcess.kill("SIGINT"));
process.on("SIGTERM", () => pythonProcess.kill("SIGTERM"));
