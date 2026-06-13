# ACTIVE_QUEUE.md

## Queue

### T001 — Review ThreadSuite generated context

Status: done
Scope:
- Reviewed generated context against repository contents.

### T002 — Crear README.md del proyecto

Status: done
Scope:
- Created `README.md` with purpose, installation, execution, controls, scripts, tests, and asset policy.

### T003 — Agregar manifiesto de dependencias

Status: done
Scope:
- Created `requirements.txt` with app, test, and optional helper-script dependencies.

### T004 — Agregar `.gitignore`

Status: done
Scope:
- Created `.gitignore` for Python artifacts, virtualenvs, logs, temporary outputs, editor files, and large 3D assets.

### T005 — Reorganizar estructura del proyecto

Status: done
Scope:
- Created `app/`, `scripts/`, `tests/`, and `assets/`.
- Moved helper scripts to `scripts/` and large sample assets to `assets/`.

### T006 — Reemplazar rutas absolutas por argumentos CLI

Status: done
Scope:
- Rewrote helper scripts to use `argparse` instead of local absolute paths.

### T007 — Mejorar logging y manejo de errores

Status: done
Scope:
- Added `logging` in `main.py` with stacktraces written to `app_log.txt` and friendly UI messages.

### T008 — Refactorizar `main.py` en módulos

Status: done
Scope:
- Added `app/mesh_io.py`, `app/selection.py`, and `app/extraction.py`.
- `main.py` now delegates loading/conversion, selection helpers, and plug/socket extraction.

### T009 — Corregir carga de escenas 3MF/OBJ con transforms

Status: done
Scope:
- `app/mesh_io.py` converts `trimesh.Scene` to a single mesh while applying scene graph transforms.

### T010 — Agregar validación robusta de mallas

Status: done
Scope:
- Added validation for empty meshes, non-triangular operations, invalid selections, full-mesh selection, extrusion depth, missing boundary data, and normals.

### T011 — Agregar exportación de piezas

Status: done
Scope:
- Added menu actions to export the latest plug and current body/socket mesh.

### T012 — Convertir pruebas manuales en tests automatizados

Status: done
Scope:
- Added `pytest.ini` and automated tests for selection and mesh conversion.
- Replaced legacy manual local-path tests with non-executing notes.

### T013 — Mejorar UX de selección y extracción

Status: done
Scope:
- Added selected-face counter, invert selection, undo last extraction, and export menu actions.

### T014 — Decidir política de assets grandes

Status: done
Scope:
- Documented policy in `README.md` and `.gitignore`.
- Moved large local assets to `assets/`.

### T015 — Revisar y actualizar continuidad ThreadSuite

Status: done
Scope:
- Updated `STATE.md`, `CONTEXT.md`, and this queue after implementation.

### T016 — Proyecto: migrar Split3r a Blender como add-on

Status: in-progress
Scope:
- Crear un add-on Python de Blender que use Blender como motor robusto de selección, Solidify y Boolean EXACT.
- Mantener el prototipo PyVista como referencia, pero dejar de parchar el core de extracción manual.
- Primer prototipo creado en `blender_split3r_addon/`.

### T017 — Diseñar arquitectura Split3r-Blender

Status: done
Scope:
- Arquitectura recomendada: add-on Python de Blender + operadores nativos de Blender (`bmesh`, `Solidify`, `Boolean EXACT`) + export STL.
- El boolean queda opcionalmente sin aplicar para inspeccionar cutter/modifier antes de destruir geometría.
- Futura integración Threadwell puede añadirse como panel separado o herramientas de automatización.

### T018 — Prototipo mínimo de add-on Blender para Split3r

Status: done
Scope:
- Creada carpeta `blender_split3r_addon/`.
- Implementado `__init__.py` instalable en Blender.
- Agregado panel `N Panel > Split3r`.
- Incluye Smart Shell Select, Create Plug + Socket, y export STL de objetos seleccionados.

### T019 — Agregar herramientas Blender para Threadwell

Status: pending
Scope:
- Diseñar tools futuras: `blender_get_scene`, `blender_get_selected_objects`, `blender_run_python`, `blender_create_material`, `blender_export_scene`.
- Evaluar extensión TypeScript de Threadwell que registre estas tools y se comunique con Blender.

### T020 — Validar flujo de seguridad y UX en Blender

Status: pending
Scope:
- Agregar confirmación explícita antes de ejecutar scripts Python generados.
- Mostrar preview del código antes de ejecutarlo.
- Registrar logs de comandos y respuestas.
- Probar instalación manual del add-on en Blender.
