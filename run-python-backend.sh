#!/bin/bash

# Start Python FastAPI backend
# Vite dev server should be started separately or via proxy

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Start Vite in background for development
npx vite --port 5173 &
VITE_PID=$!

# Wait a bit for Vite to start
sleep 3

echo "Starting Python FastAPI backend on port 5000..."
cd server_py
python app.py

# Cleanup
trap "kill $VITE_PID 2>/dev/null" EXIT
