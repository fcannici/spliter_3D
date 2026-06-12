# CONTEXT

## Project

Split3r Clone

## Purpose

Python desktop application for loading 3D meshes (`.stl`, `.obj`, `.3mf`), selecting mesh faces, and extracting a plug/socket pair for 3D-printing workflows.

## Architecture map

- Entrypoint: `main.py`
- App modules:
  - `app/mesh_io.py`: mesh loading, scene transform preservation, PyVista/Trimesh conversion, validation.
  - `app/selection.py`: adjacency map and smart-shell flood-fill selection.
  - `app/extraction.py`: selected-region plug/socket mesh generation.
- Helper scripts: `scripts/`
- Tests: `tests/`
- Local/sample assets: `assets/`

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run app:

```bash
python main.py
```

Validate:

```bash
python -m py_compile main.py app/*.py scripts/*.py tests/*.py && pytest -q
```

## Conventions

- Keep UI wiring in `main.py`; move reusable mesh/selection/extraction logic into `app/`.
- Helper scripts should use CLI arguments; no machine-local absolute paths.
- Large `*.stl` and `*.3mf` files are ignored by default. Use `assets/` intentionally or external/LFS storage for heavy models.
- Preserve user-authored continuity files unless explicitly updating project state.

## Validation strategy

- Use lightweight syntax checks and `pytest` for non-GUI logic.
- Manually smoke test the Qt/PyVista UI with real models after code changes involving interaction, rendering, or extraction.

## Known risks

- Plug/socket geometry generation depends on PyVista/VTK boundary metadata and may need more robust handling for non-manifold or unusual meshes.
- GUI behavior is not covered by automated tests.
- Optional video/audio helper scripts require extra dependencies and external services for transcription.
