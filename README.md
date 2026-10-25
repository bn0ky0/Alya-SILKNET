# Alya SILKNET

Alya SILKNET is a Windows desktop workspace for recording entities, relationship claims and their sources. It works offline and keeps its database on the device.

## Download

[Download the latest Alya SILKNET release](https://github.com/bn0ky0/Alya-SILKNET/releases/latest) from GitHub. The release page includes the portable ZIP and the per-user installer.

## What is included

- Entity records for people, social profiles, organizations, websites, emails, phone numbers, locations, documents and custom types. Person records have an optional role that floats above their graph card, and profile photos can be chosen or dropped onto the photo control from Explorer.
- Directional relationship claims with dates, notes, verification status and confidence notes.
- An interactive graph with movable nodes, directed edges and compact, polished arrowheads, name/type filters, zoom, right-drag panning, Shift-drag linking and card-port linking. Create multiple named graph workspaces with independent card membership and layouts, and drag entity cards from the right-hand palette. Every workspace can be renamed or deleted, and the app always keeps at least one workspace available. Removing a card keeps its claim lines saved; when you bring it back, choose **Card only** or **Restore connections**. Remove a relationship claim from its edit dialog, the edge context menu, or with **Delete** / **Backspace**; the entities and evidence sources stay in the workspace.
- Local sources linked to entities and claims. Source links show the status of the claim they support.
- Search across saved entities, relationship claims and sources, with type, tag and verification filters.
- JSON workspace import/export and CSV entity import/export. Imports show validation errors and likely duplicates before writing. New IDs are assigned locally and claim links are remapped.
- Six saved appearances: dark, light, Alya pink, dark red, dark purple and dark green. Dark and light follow a limited accent palette (baby blue, violet, crimson, mint, amber). Alya pink adds a 64 px, face-only Alya-sama as a free-floating pet: drag her anywhere on the desktop, even outside the app, and click her for a speech bubble that sits above her head and flips only when a screen edge would hide it. Blossoms fall across the window. A two-second branded intro follows the selected theme, can be skipped with a click or `Esc`, `Space` or `Enter`, and reveals the workspace at launch. Page changes slide and fade in the direction of the selected tab, and every workspace tab keeps its own transition and scroll state.
- One UI scale slider that adjusts text and button sizing only, from 75% to 100% (90% by default), without resizing cards or the window.
- ZIP backups containing the SQLite workspace and local profile images. Restores verify the database and create a safety backup first.
- A Windows folder build made with PyInstaller, plus an optional Inno Setup installer. The portable folder can be copied anywhere; the installer adds Start Menu and optional desktop shortcuts. Launching the executable while Alya SILKNET is already running brings the open window to the front instead of starting a second copy.
- An update check in **About** that reads the latest GitHub release when the page opens, with a button to open the release page when a newer version is available.

Alya SILKNET stores workspace data on the device and does not configure online research providers, remote sync or analytics. Opening a saved URL and exporting a file are explicit actions. Opening **About** checks the public GitHub Releases API for a newer version; no workspace data is sent. It does not match identities or infer relationships from names, photos or usernames. A valid social profile URL does not establish who controls the account.

## Requirements

- Python 3.12 or newer for development.
- Windows 10 or newer for the provided desktop build.
- PySide6 Essentials, installed with the project dependencies.

## Run from source

From this directory:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m silknet
```

Run the checks:

```powershell
pytest --basetemp=.pytest-tmp
ruff check src tests
ruff format --check src tests
```

Use `Ctrl+1` through `Ctrl+7` to open the sidebar pages in order. `Ctrl+K` focuses the workspace search field. `Ctrl+B` collapses or reopens the sidebar. `F11` toggles full screen, and `Escape` leaves full screen.

## Windows desktop build

Install the build extra and run the PowerShell build script:

```powershell
python -m pip install -e ".[build]"
.\scripts\build_windows.ps1
```

The build is written to `dist\SILKNET\SILKNET.exe`. Copy the complete `dist\SILKNET` folder when moving the app; the executable uses files beside itself. The app keeps its workspace in the normal SILKNET data folder, shared by source and packaged launches. Add `-Console` to the build command when you need startup tracebacks in a terminal.

To build a Windows installer, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) and run:

```powershell
.\scripts\build_installer.ps1
```

The installer is written to `dist\installer\installer.exe`. It installs per user by default, so administrator rights are not required, and includes an uninstaller, a Start Menu shortcut and an optional desktop shortcut.

## Update checks

The **About** page has a **Check for updates** button. It compares the installed version with the latest public release in the [`bn0ky0/Alya-SILKNET`](https://github.com/bn0ky0/Alya-SILKNET) repository. The check runs once when About opens and can be repeated with the button. It only reads release metadata from the GitHub API and never uploads workspace data. When a newer release exists, About shows its version and a button that opens the release page.

The app remains fully usable offline. If GitHub cannot be reached, About reports that the check failed and leaves the workspace untouched.

## Local data and backups

On Windows, SILKNET stores:

- The SQLite database and profile images under `%LOCALAPPDATA%\SILKNET`.
- Appearance settings and logs under `%APPDATA%\SILKNET`.

The database schema is upgraded in place with ordered migrations. It is not encrypted by SILKNET. Use **Settings → Create backup** to save a ZIP containing the database and profile images. **Restore backup** replaces the open workspace after confirmation and creates a safety backup in the local data folder first. Appearance preferences remain in the separate configuration folder.

For an isolated workspace during development, set `SILKNET_CONFIG_DIR` and `SILKNET_DATA_DIR` to directories you control before launching.

## Import and export

- **JSON** exports entities, claims, sources and custom entity type definitions.
- **CSV** exports entity rows only. It does not include claims, sources or their links.
- Imports skip duplicate entities with the same type and case-insensitive name. Sources are matched by type, title and location. Imported relationship endpoints and evidence links are mapped to the resulting local records.
- JSON exports include local image paths, not image bytes. Use the ZIP backup when moving a workspace with its profile images.

## Troubleshooting

- If the app does not open, launch `python -m silknet` from the source directory to see startup errors, or check `%APPDATA%\SILKNET\logs\silknet.log`.
- If launching the executable appears to do nothing, check whether Alya SILKNET is already open. A second launch activates the existing window and exits.
- To diagnose a packaged build, run `scripts\build_windows.ps1 -Console` and read the traceback shown by the console executable.
- If the database cannot be opened after an interrupted update, restore the latest ZIP backup from **Settings → Restore backup**.
- If a profile image does not appear after importing JSON on another device, restore from a ZIP backup instead; JSON does not embed the image file.
- If Windows blocks the downloaded build, use the copied project folder from a trusted location and confirm the file came from the intended distributor.

## Project layout

- `src/silknet/core/` contains models, validation and domain errors.
- `src/silknet/database/` contains SQLite migrations, connections and repositories.
- `src/silknet/services/` contains domain operations, search, data exchange, backups and optional provider contracts.
- `src/silknet/graph/` contains the investigation graph model.
- `src/silknet/ui/` contains the desktop pages and dialogs.
- `tests/` covers database migrations, persistence, graph and family logic, profile images, provenance, data exchange, backups and UI wiring.
- `docs/manual-ui-checklist.md` lists the desktop interaction checks.

## Privacy and limits

Records, profile images, settings and logs stay in local files unless the user explicitly exports or opens a URL. Local storage is not encrypted by SILKNET. External provider integrations are not configured. Search only examines saved workspace data; it does not perform online lookups. The About page contacts the public GitHub Releases API to check for updates; it sends no workspace data.

## License

Alya SILKNET is released under the MIT License. See [LICENSE](LICENSE).

