---
status: active
source: threadsuite-bootstrap
updated: 2026-06-12
---

# STATE

Split3r Clone is now identified as a Python desktop app for 3D mesh face selection and plug/socket extraction for 3D-printing workflows.

## Current status

- Repository reviewed and generated context confirmed.
- Project scaffolding added: `README.md`, `requirements.txt`, `.gitignore`, `pytest.ini`.
- Code reorganized into `app/`, `scripts/`, `tests/`, and `assets/`.
- `main.py` now uses reusable modules for mesh IO, selection, and extraction.
- Helper scripts now use CLI arguments instead of machine-local absolute paths.
- Large sample models moved to `assets/` and ignored by default for future large assets.
- Lightweight validation passed: `python -m py_compile main.py app/*.py scripts/*.py tests/*.py && pytest -q`.

## Next

Open project queued: integrate Threadwell into Blender as a Python add-on bridge. First practical step: design the Blender add-on architecture and prototype a minimal panel that can send prompts to Threadwell via CLI or RPC.
