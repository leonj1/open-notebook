# Railway Deployment

This guide shows how to deploy Open Notebook to Railway using the single‑container image (frontend + API + SurrealDB) with Next.js proxying to the backend internally.

## Overview

- Build: Docker (uses `Dockerfile.single`)
- Public port: Railway’s `$PORT` (Next.js UI)
- API: Internal on `localhost:5055` (proxied by Next.js via `/api/*`)
- Database: SurrealDB running in the same container, data persisted via Railway Volumes

## 1) Add Config-as-Code

The repository already includes `railway.json`:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile.single" },
  "deploy": { "healthcheckPath": "/", "restartPolicyType": "ALWAYS" },
  "service": "open-notebook"
}
```

This tells Railway to build from `Dockerfile.single` (single-container deployment) and to consider `/` healthy.

## 2) Create the Service

You can deploy from the UI or CLI:

- Connect your GitHub repo to Railway and select this project.
- Railway will detect `railway.json` and build using `Dockerfile.single`.

## 3) Attach Volumes (Persistence)

Attach two volumes to keep notebooks and the database across restarts:

- Mount `/app/data` (user notebooks and generated assets)
- Mount `/mydata` (SurrealDB data)

You can do this in the Railway UI under your service → Volumes.

## 4) Environment Variables

Set these variables on the service:

Required (recommended):

- `OPEN_NOTEBOOK_PASSWORD` — protect your instance (pick a strong value)
- `OPENAI_API_KEY` — optional but recommended to start; add others as needed

Single‑container DB (already defaulted by image, set explicitly for clarity):

- `SURREAL_URL=ws://localhost:8000/rpc`
- `SURREAL_USER=root`
- `SURREAL_PASSWORD=root`
- `SURREAL_NAMESPACE=open_notebook`
- `SURREAL_DATABASE=production`

Networking:

- `API_URL=https://${RAILWAY_PUBLIC_DOMAIN}`
  - Makes the browser call `https://<your-app>.railway.app/api/*`, which Next.js rewrites to the backend.
- `INTERNAL_API_URL=http://127.0.0.1:5055` (optional; default is `http://localhost:5055`)

Other providers (optional):

- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, etc.
- `OLLAMA_API_BASE` if you point to a remote/local Ollama instance

Tip: use the provided `.env.railway.example` as a reference.

## 5) Ports and Healthchecks

- Railway injects `PORT` — the Next.js UI listens on that value automatically.
- The API listens on `5055` inside the container and is reachable via `/api/*` on the public domain.
- Healthcheck is `/` (UI). Once healthy, you can open the app.

## 6) First Run Checklist

1. Confirm the app loads on `https://<your-app>.railway.app`.
2. Log in if `OPEN_NOTEBOOK_PASSWORD` is set.
3. Open Settings → Models and add at least one provider (OpenAI works out of the box).
4. Create your first notebook and add a source.

## 7) Troubleshooting

- Blank screen or connection error:
  - Ensure `API_URL` is set to `https://${RAILWAY_PUBLIC_DOMAIN}` (no trailing `/api`).
  - Confirm both volumes are attached and the service is healthy.
- API unreachable:
  - Don’t expose `5055` directly; use the UI domain with `/api/*` (Next.js rewrites to the backend).
- Authentication issues:
  - If you set `OPEN_NOTEBOOK_PASSWORD`, all API calls require `Authorization: Bearer <password>`; the UI handles this once you log in.
- Performance:
  - Increase service resources in Railway. For podcast TTS concurrency, tune `TTS_BATCH_SIZE`.

## 8) What’s Running Inside the Container

- SurrealDB (port 8000) → `SURREAL_URL=ws://localhost:8000/rpc`
- FastAPI backend (port 5055)
- Next.js UI (port `$PORT`, proxied by Railway) → proxies `/api/*` → backend

With this setup, Railway only needs to expose the UI port while the API stays internal.

