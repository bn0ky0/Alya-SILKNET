# `CONTRIBUTING.md` 💾

> patches welcome. chaos not guaranteed.

Thanks for wanting to contribute to **Alya SILKNET**! 🌸  
Keep it clean, keep it local, and please don't summon bugs on purpose.

## ⚙️ Boot Sequence

**Requirements:** Python 3.12+ and Windows for the desktop app.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Launch the app:

```powershell
python -m silknet
```

## 🛠️ Rules of Engagement

- **Keep UI copy short.** Nobody wants a novel in a dialog.
- **Comment the why, not the obvious.**
- **Keep it local-first.** Network access must be opt-in and visible.
- **Protect user data.** Never commit personal records, exports, profile pictures, local settings, databases, or backups.
- **Respect `.gitignore`.** Generated builds and local files stay out of Git.
- **Keep changes focused.** One fix is better than 47 unrelated experiments.
- **No sneaky telemetry.** Don't add analytics or hidden network requests.
- **Be nice.** Critique the code, not the human writing it.

## 🧪 Before You Push

Run the checks:

```powershell
ruff check src tests
ruff format --check src tests
pytest --basetemp=.pytest-tmp
```

Fix failures before opening a pull request. Green checks = happy Alya. ✅

## 🔀 Pull Requests

1. Explain what changed and why.
2. Include steps to reproduce bug fixes.
3. Add or update tests when appropriate.
4. Include screenshots for meaningful UI changes.
5. Mention anything that still needs work.

Small, readable pull requests are easier to review and less likely to summon mysterious regressions.

## 🔒 The Golden Rule

SILKNET is a **local-first desktop workspace**.

Workspace data stays on the device unless the user explicitly chooses to export it or open something externally. Don't weaken that guarantee without a clear, documented reason.

**Build cool stuff. Respect privacy. Don't leak anyone's stuff.** 🌸

---

<p align="center">
  <sub>Made with curiosity, caffeine, and questionable sleep schedules.</sub>
</p>
