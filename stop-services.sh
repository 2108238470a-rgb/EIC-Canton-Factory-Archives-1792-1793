#!/bin/bash

echo "🛑 Stopping OCR Platform services..."

# Stop backend (port 8000)
echo "Stopping FastAPI backend..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
pkill -f "uvicorn.*app.main" 2>/dev/null

# Stop frontend (ports 3000 and 3001)
echo "Stopping Next.js frontend..."
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:3001 | xargs kill -9 2>/dev/null
pkill -f "next dev" 2>/dev/null

# Stop Docker containers (optional, commented by default)
# echo "Stopping Docker containers..."
# docker-compose down

echo "✅ All services stopped"

# Show status
echo ""
echo "Port status:"
lsof -i:8000 2>/dev/null || echo "  Port 8000: Free"
lsof -i:3000 2>/dev/null || echo "  Port 3000: Free"
lsof -i:3001 2>/dev/null || echo "  Port 3001: Free"
