#!/bin/bash

# Activate virtual environment if it exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "Virtual environment not found. Creating one..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r backend/requirements.txt
fi

# Start backend server in background
cd backend && python manage.py runserver &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 5

# Start frontend server in background
cd ../frontend && npm run dev &
FRONTEND_PID=$!

echo "PartsDB development servers started!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"

# Function to handle script termination
function cleanup {
    echo "Shutting down servers..."
    kill $BACKEND_PID $FRONTEND_PID
    exit 0
}

# Trap SIGINT (Ctrl+C) and call cleanup
trap cleanup SIGINT

# Keep script running
wait