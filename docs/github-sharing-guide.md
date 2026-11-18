# GitHub sharing and data setup

## Repository contents

The Git repository should contain the Python backend under `app/`, processing and analysis commands under `scripts/`, tests under `tests/`, the technical documents under `docs/`, and root project configuration (`README.md`, `pyproject.toml`, `requirements*.txt`, `.env.example`, `.gitignore`, `.dockerignore`, and `Dockerfile`). The top-level `frontend/` folder is deliberately excluded because it is teammate-owned and outside this backend repository's scope.

The local repository is on `master` with no local commits. The requested GitHub URL is configured as `origin`; an authenticated `git ls-remote --heads origin` returned no refs, indicating the remote is currently empty. No fetch, commit, or push has occurred. The authenticated account could read the repository endpoint, while unauthenticated web access returned 404; confirm **Private** in GitHub repository settings before publishing. Preserve any remote history that appears later; do not force-push.

## Runtime data and large-file decision

The application expects `datasets/processed/crowdwise.duckdb` for immediate ETM analytics. The current local database is 182,726,656 bytes (174.26 MiB). Rebuilding it requires the source CSV. The source archive is 66,145,093 bytes (63.08 MiB), and contains the 290,014,457-byte (276.58 MiB) extracted CSV plus a small macOS metadata entry. The extracted CSV is redundant if the source archive is available.

All runtime datasets, generated signal stores, and analysis outputs remain ignored by Git. This is intentional: ETM redistribution and derived-data permissions are not established in the project documentation, and the ETM source and processed database should not be placed in normal Git history. Git LFS can store files over 100 MiB technically, but it does not grant redistribution rights and private repository access does not establish those rights. Narrow Git LFS filters exist for the DuckDB and source ZIP, but both remain ignored; no dataset is staged and no LFS objects are uploaded.

For an authorized teammate data handoff, use the team's approved private file-transfer/storage service. Transfer the preprocessed DuckDB for quickest startup and place it at `datasets/processed/crowdwise.duckdb`. Its SHA-256 in this workspace is `BFA06E80336729D80FD4C862436216567521EAE8536AC494A8454B159B5B14F3`; verify the transfer with `Get-FileHash`. If they are also authorized to use the raw ETM source and need reproducible processing, the project records this source URL:

`https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip`

This endpoint was recorded in the project data-source documentation and supplied for this data by the project brief; its current availability and data redistribution permission were not re-confirmed in this upload-preparation pass. If the provider permits their use, download and verify the exact archive used in this workspace (SHA-256 `3B0D051B13A7082697DF1C0F03140611350E50B574B44E21D1FB62D4F23DF7BE`):

```powershell
New-Item -ItemType Directory -Force datasets\etm\raw | Out-Null
Invoke-WebRequest -Uri 'https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip' -OutFile datasets\etm\raw\October-Delhi.csv.zip
if ((Get-FileHash datasets\etm\raw\October-Delhi.csv.zip -Algorithm SHA256).Hash -ne '3B0D051B13A7082697DF1C0F03140611350E50B574B44E21D1FB62D4F23DF7BE') { throw 'ETM archive checksum mismatch' }
Expand-Archive -LiteralPath datasets\etm\raw\October-Delhi.csv.zip -DestinationPath datasets\etm\raw
```

If that link is unavailable, use the approved private transfer service. Do not distribute the archive/database unless the data owner confirms permission. Extract the archive to `datasets/etm/raw/`, then rebuild to a separate output first:

```powershell
Expand-Archive -LiteralPath datasets\etm\raw\October-Delhi.csv.zip -DestinationPath datasets\etm\raw
python -m scripts.process_etm --csv datasets\etm\raw\October-Delhi.csv --database datasets\processed\crowdwise_rebuilt.duckdb
```

After reviewing the generated quality report, point the API at that database for the session:

```powershell
$env:CROWDWISE_DATABASE_PATH = (Resolve-Path datasets\processed\crowdwise_rebuilt.duckdb).Path
```

The project records the source download URL above, but there is no verified, approved URL for redistributing the ETM or DuckDB to teammates. Do not upload the data to a public release or third-party host until the data owner has confirmed redistribution terms. The DTC timetable PDF is not needed to run the backend, is not validated GTFS, and is excluded. No Delhi GTFS static feed is currently available; journey routing, geofenced presence and live vehicles remain unavailable until authorized data is separately acquired and validated.

## Create a private GitHub repository and push

Git and Git LFS are installed on the preparation computer (Git 2.55.0 and Git LFS 3.7.1 were detected). The supplied GitHub URL is already configured as `origin` and currently has no refs. Confirm it is **Private** in GitHub settings before upload. These commands explicitly stage backend files and do not stage the frontend or ignored data:

```powershell
git add .gitignore .gitattributes .dockerignore .env.example Dockerfile README.md pyproject.toml requirements.txt requirements-dev.txt
git add app scripts tests docs
git status --short
git diff --cached --stat
git diff --cached --name-only
git ls-remote --heads origin
```

Review the staged file list and confirm no `frontend/`, `.env`, database, raw data or generated outputs appear. Check for secrets before committing. Then:

```powershell
git commit -m "Prepare CrowdWise backend for team integration"
git push -u origin main
```

Git author name and email are not configured in this local repository yet; set them locally before committing, using the account identity/email you want recorded. The approved upload branch is `main`. Do not use `--force`. If `git ls-remote --heads origin` shows any branch, fetch and reconcile that history before pushing; never overwrite it.

Git LFS is installed and initialized locally. `.gitattributes` contains narrow LFS filters for only the DuckDB database and ETM source ZIP; these files remain Git-ignored and are **not staged or uploaded**. `git lfs ls-files` is empty, so the repository currently has no LFS objects. This prevents an explicitly approved future add from placing either binary into normal Git history. The extracted 276.58 MiB CSV is redundant and has no LFS rule.

GitHub's current documentation says a single standard Git file above 100 MiB is blocked; Git LFS is required above that limit. GitHub recommends a file-sharing service for large databases. GitHub Free and Pro currently include 10 GiB LFS storage and 10 GiB monthly bandwidth, and their per-file LFS maximum is 2 GB. If both current binaries were approved for LFS, they would consume about 237.34 MiB of storage and about that much bandwidth for each full teammate clone (roughly 43 clones within 10 GiB, before any other LFS use). New file versions add storage use. These quotas are account-level and can change; check [GitHub LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs) and [large-file guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) before opting in.

The database is better transferred via the team's approved private file-sharing service, both because GitHub discourages database files in Git and because ETM redistribution rights are undocumented. Never force-add ignored data simply to make a clone appear complete. If data rights are confirmed and you decide to use LFS, review the two `.gitattributes` patterns and LFS billing/quota, then explicitly force-add only approved files after the review.

## Teammate Windows setup

After the private repository is pushed, a teammate with GitHub access can clone the backend source:

```powershell
git clone <PRIVATE_GITHUB_REPOSITORY_URL> CrowdWise
Set-Location CrowdWise
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

The clone does not contain ETM data or the DuckDB. Create the data directory with `New-Item -ItemType Directory -Force datasets\processed | Out-Null`, then obtain the authorized DuckDB through the team's private transfer channel and place it at `datasets\processed\crowdwise.duckdb`; verify SHA-256 `BFA06E80336729D80FD4C862436216567521EAE8536AC494A8454B159B5B14F3`. Alternatively, if data use is authorized, download the source archive using the recorded link/checksum instructions above, extract it, and run the ETM pipeline to build a database. Without one of these data setup paths, the application can start but ETM readiness/analytics will report unavailable.

Start and verify:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/capabilities
Invoke-RestMethod http://127.0.0.1:8000/api/v1/analytics/overview
```

Swagger UI is at `http://127.0.0.1:8000/docs`; the exact OpenAPI document is at `http://127.0.0.1:8000/openapi.json`. Copyable API examples and response semantics are in `docs/API_QUICK_REFERENCE.md` and `docs/FRONTEND_HANDOFF.md`.

Run backend checks from the repository root:

```powershell
python -m pytest -q
python -m compileall -q app scripts tests
python -m pip check
```

## Optional live data and secret handling

The service starts without a live data URL or credentials. To enable an authorized GTFS-Realtime VehiclePositions source, the server operator must first receive provider authorization, then set `CROWDWISE_GTFS_RT_URL`, `CROWDWISE_GTFS_RT_API_KEY` (if required), and the provider-documented auth mode/header in a local untracked `.env` or deployment secret manager. Use HTTPS. Never put a real value in `.env.example`, source code, GitHub issues, frontend code, or shared logs. Set the exact frontend origin(s) in `CROWDWISE_CORS_ORIGINS` on the backend server.

Optional live feeds require a compatible authorized static GTFS feed in the processed DuckDB for identity matching. Current project configuration has neither, so a normal clone must show unavailable live features rather than fabricate positions. Do not request or invent credentials as part of setup.
