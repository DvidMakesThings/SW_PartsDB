@echo off
REM Activate virtual environment if it exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Creating one...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r backend\requirements.txt
)

REM Start backend server
start cmd /k "cd backend && python manage.py runserver"

REM Wait a moment for backend to start
timeout /t 5

REM Start frontend server
start cmd /k "cd frontend && npm run dev"

echo PartsDB development servers started!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173