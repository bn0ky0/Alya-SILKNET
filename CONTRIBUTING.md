# Contributing

SILKNET is a local desktop app. Keep workspace records on the device unless a person using the app chooses to export or open something.

## Development setup

Use Python 3.12 or newer, create a virtual environment, and install the development extra:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run the app with `python -m silknet`. Ruff is used for formatting and linting. Generated builds, local databases, logs and backups are excluded from Git by `.gitignore`.

## Changes

- Keep UI copy direct and short.
- Add comments when they explain a decision that is not clear from the code.
- Keep network access opt-in and visible to the person using the app.
- Do not commit personal workspace data, exports, profile images or local settings.
