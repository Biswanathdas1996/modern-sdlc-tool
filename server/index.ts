import { spawn } from "child_process";
import path from "path";

const isDev = process.env.NODE_ENV === "development";

// Start Vite dev server in development mode
let viteProcess: ReturnType<typeof spawn> | null = null;
if (isDev) {
  console.log("Starting Vite dev server...");
  viteProcess = spawn("npx", ["vite", "--port", "5173", "--host"], {
    stdio: "inherit",
    shell: true
  });
  
  viteProcess.on("error", (err) => {
    console.error("Failed to start Vite:", err);
  });
}

// Wait a moment for Vite to start, then launch Python backend
setTimeout(() => {
  console.log("Starting Python FastAPI backend...");
  const pythonProcess = spawn("python", ["main.py"], {
    cwd: path.join(process.cwd(), "server_py"),
    stdio: "inherit",
    env: { 
      ...process.env, 
      PYTHONUNBUFFERED: "1",
      NODE_ENV: isDev ? "development" : "production"
    }
  });

  pythonProcess.on("error", (err) => {
    console.error("Failed to start Python backend:", err);
    process.exit(1);
  });

  pythonProcess.on("close", (code) => {
    if (viteProcess) viteProcess.kill();
    process.exit(code || 0);
  });

  const cleanup = () => {
    pythonProcess.kill("SIGINT");
    if (viteProcess) viteProcess.kill("SIGINT");
  };

  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);
}, isDev ? 2000 : 0);
