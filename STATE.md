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
- Product-direction V2 started as a standalone Smart Paint app in `split3r_standalone/`, with Include/Exclude marks and conservative Smart Paint expansion.
- Lightweight validation passed: `python -m py_compile standalone_main.py split3r_standalone/*.py blender_split3r_addon/__init__.py main.py app/*.py scripts/*.py tests/*.py && pytest -q`.

## Next

Continue Split3r V2 standalone: run `python standalone_main.py`, load the real 3MF, validate Include/Exclude painting and Smart Paint Expand against the manual reference selection, then wire extraction to Blender headless for plug/socket generation.
