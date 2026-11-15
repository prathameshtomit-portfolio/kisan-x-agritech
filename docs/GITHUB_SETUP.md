# GitHub upload and run guide

## Prepare the repository

1. Use the team's designated shared repository if one already exists; avoid creating a duplicate project repository.
2. Review the tracked files and confirm that `.env`, SQLite databases, payment uploads, `.venv`, `work/` and `outputs/` are excluded by `.gitignore`.
3. Open the agreed GitHub repository, then upload the project root (the directory containing `README.md`, `backend/`, `docs/`, and `Dockerfile`). Do not upload extracted staging folders or generated release ZIPs.
3. The GitHub Actions workflow runs backend tests, Python compilation, and JavaScript syntax checks on pushes and pull requests.

If using Git locally, from the project root:

```bash
git init
git add .
git status --short
git commit -m "Prepare KISAN-X prototype"
git branch -M main
git remote add origin <team-repository-url>
git push -u origin main
```

Inspect `git status` before the first commit. Never commit `.env`, owner PINs, databases containing farmer records, receipt/QR uploads, or real farm coordinates.

## Run the full stack locally

Follow the root `README.md` quick-start, then start the FastAPI app from `backend/`. The frontend is served from the same origin, so local web features and API requests work together at `http://127.0.0.1:8000/`.

## Run with Docker

Build and launch a local container from the repository root:

```bash
docker build -t kisanx:local .
docker run --rm -p 8000:8000 -e KISANX_OWNER_PIN=replace-with-a-private-pin kisanx:local
```

The container's default SQLite database and uploaded payment images live in its writable filesystem. They disappear when the container is removed unless persistent storage is mounted. For a shared deployment, configure a managed PostgreSQL database, private `KISANX_OWNER_PIN`, HTTPS, persistent private receipt storage, backups, and an exact CORS allowlist before enabling owner payment operations.

## GitHub Pages limitation

GitHub Pages can host static files only. It cannot run FastAPI, save farm records to the backend database, call backend-only integrations, or securely handle owner payment verification. This app's web UI is served by FastAPI; publishing the HTML alone does not make the backend-dependent features work. Host the full-stack service on a Python-capable platform or run the Docker image, and point users to that service URL.

## Before real farmers use it

This is a hackathon prototype without farmer accounts or per-farmer authorization. Do not expose real farm profiles or payment records on a public deployment until authentication, access control, consent, private storage, database backups, rate limits, monitoring and a data-retention/deletion process are implemented and reviewed. See `docs/FRONTEND_BACKEND_INTEGRATION.md` and `docs/AGRICULTURE_ADVISORY_STANDARD.md` for product and agronomy limits.
