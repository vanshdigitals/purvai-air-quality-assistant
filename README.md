# Purvai

**Know the air. Act in time.**

Purvai is an AI-powered urban air quality and personal safety assistant that turns official air data into clear, deterministic daily actions for families in Indian cities.

## Quick start

### PowerShell (Windows)

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend; uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

### Bash (Linux / macOS)

```bash
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend && npm ci && npm run dev
```

For full documentation, architecture, and setup details, see [docs/README.md](docs/README.md).
