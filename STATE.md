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
- PyVista/VTK extraction improved but showed architectural limits on complex organic 3MF meshes.
- Recommended V2 started as a Blender add-on in `blender_split3r_addon/` using `bmesh`, `Solidify`, and `Boolean EXACT`.
- Lightweight validation passed: `python -m py_compile blender_split3r_addon/__init__.py main.py app/*.py scripts/*.py tests/*.py && pytest -q`.

## Next

Install and smoke-test `blender_split3r_addon/` in Blender with the Aztec whistle 3MF: Smart Shell selection, plug Solidify, socket Boolean EXACT, and STL export.
