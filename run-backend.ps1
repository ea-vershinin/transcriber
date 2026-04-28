cd $PSScriptRoot\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload