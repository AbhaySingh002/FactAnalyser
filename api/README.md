# Fact Knowledge Layer — API

Stateless FastAPI service deployed on Render with PostgreSQL + pgvector and Cloudflare R2 storage.

## Run Locally

### 1. Prerequisites & Environment
Ensure you have Python 3.11+ installed. Create your virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the environment template and set your credentials:
```bash
cp .env.example .env
```

Required environment variables:
- `DATABASE_URL`: PostgreSQL connection string with pgvector extension enabled.
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`: Cloudflare R2 credentials.
- `R2_PUBLIC_URL`: Base URL for public reads of uploaded PDFs and page PNGs.
- `GROQ_API_KEY`: Groq API key for Llama 3.3 and Llama 4 Scout.
- `GEMINI_API_KEY`: Google Gemini API key for fallback vision and 768-dim embeddings.
- `FRONTEND_ORIGIN`: Allowed CORS origin (default `*`).

### 2. Apply Database Schema
Apply the DDL schema to your PostgreSQL database:

```bash
psql $DATABASE_URL -f api/schema.sql
```

### 3. Start the Server
Run the FastAPI development server with uvicorn:

```bash
uvicorn api.main:app --reload --port 8000
```

The API docs are available at `http://localhost:8000/docs`.

### 4. Test Upload & Pipeline
Upload a financial/legal PDF to trigger R2 streaming, layout parsing, fact extraction, and reconciliation:

```bash
curl -F "file=@starter-datasets/delhivery/01-delhivery-prospectus-2022-excerpt.pdf" http://localhost:8000/documents
```

Check pipeline status:
```bash
curl http://localhost:8000/jobs/{job_id}
```
