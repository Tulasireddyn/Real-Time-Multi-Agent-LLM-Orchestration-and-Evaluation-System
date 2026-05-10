# Stop existing processes
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Setup Python Environment
if (!(Test-Path venv)) {
    python -m venv venv
}
.\venv\Scripts\activate
pip install -r requirements.txt

# Ensure SQLite DB is initialized
python -c "from core.db import init_db; init_db()"

# Start Backend in background
Start-Job -Name "MultiAgentAPI" -ScriptBlock { 
    cd "c:\Users\tulas\Downloads\project\Real-Time Multi-Agent LLM Orchestration and Evaluation System"
    .\venv\Scripts\python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 
}

# Setup Frontend
cd frontend
npm install
npm run dev
