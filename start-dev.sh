#!/bin/bash

# Start the Python backend and Vite dev server concurrently
# The Python server runs on port 5000 and proxies non-API requests to Vite on port 5173

# Start Vite dev server in the background
npm run dev:vite 2>&1 | sed 's/^/[Vite] /' &
VITE_PID=$!

# Give Vite a moment to start
sleep 2

# Start Python backend
cd server_py
python app.py  2>&1 | sed 's/^/[Python] /'

# Cleanup on exit
trap "kill $VITE_PID 2>/dev/null" EXIT
