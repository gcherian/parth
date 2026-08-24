# Parth

A personal AI mentor for every Indian child — a FastAPI server (web app + API)
plus a Flutter mobile app.

## Quick start

Clone the repo, then run **one script** to build everything and start Parth.

### macOS / Linux

```bash
./setup.sh
```

### Windows

```powershell
.\setup.ps1
```

(If PowerShell blocks the script: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or run it via Git Bash / WSL with `./setup.sh` instead.)

Either script will:

1. Create a Python virtual environment and install server dependencies
2. Generate `server/.env` from a template on first run (edit it to add
   `ANTHROPIC_API_KEY` if you want Claude cloud instead of local Ollama)
3. Start Postgres via Docker and apply the DB schema
4. Start Ollama if it's installed (optional — skipped with a warning if not)
5. Start the Parth server and print its URLs (web app, monitor, demo,
   playground, API docs)
6. Run `flutter pub get` in `app/` so the mobile app is ready to launch

Both scripts are **safe to re-run** — every step is idempotent.

### Options

| Flag (bash) | Flag (PowerShell) | Effect |
|---|---|---|
| `--server-only` | `-ServerOnly` | Skip the Flutter/mobile step entirely |
| `--mobile` | `-Mobile` | Also launch the app on a connected device/emulator |

## Prerequisites

- **Python 3.11+**
- **Docker** (Docker Desktop on Mac/Windows) — used to run Postgres
- **Ollama** (optional) — local LLM backend; without it, set
  `ANTHROPIC_API_KEY` in `server/.env` to use Claude cloud instead
- **Flutter SDK** (optional, only needed for the mobile app) — see
  https://docs.flutter.dev/get-started/install. The app currently ships
  with Android platform files only; run it on an Android emulator/device,
  or `flutter create --platforms=ios .` inside `app/` to add iOS support.

## Running the mobile app manually

```bash
cd app
flutter pub get
flutter run          # picks a connected device or running emulator
```

The Flutter app talks to the server started by `setup.sh`/`setup.ps1` — make
sure that's running first, and that the device/emulator can reach your
machine's IP (printed in the setup banner as `Web App`).

## Stopping the server

The setup script prints the exact stop command in its final banner
(`kill $(cat /tmp/parth.pid)` on Mac/Linux, or the equivalent
`Stop-Process` line on Windows).

## Repo layout

- `server/` — FastAPI backend + static web UI (`main.py`, `docs`, `monitor`,
  `demo`, `playground`, ...)
- `app/` — Flutter mobile app
- `docs/` — design notes
