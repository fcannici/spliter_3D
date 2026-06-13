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

### T016 — Proyecto: integrar Threadwell a Blender como add-on

Status: pending
Scope:
- Crear un add-on Python de Blender que actúe como puente hacia Threadwell.
- Empezar con una versión mínima: panel en Blender, campo de prompt, botón para enviar a Threadwell y área para ver respuesta.
- Usar inicialmente Threadwell CLI (`thread -p`) o evaluar `thread --mode rpc` para sesión persistente.

### T017 — Diseñar arquitectura Threadwell-Blender

Status: pending
Scope:
- Definir si la integración inicial usa CLI, RPC o servidor local.
- Documentar arquitectura recomendada: Blender add-on Python + Threadwell RPC + futura extensión Threadwell con herramientas Blender.
- Definir límites de seguridad para ejecutar código generado dentro de Blender.

### T018 — Prototipo mínimo de add-on Blender para Threadwell

Status: pending
Scope:
- Crear carpeta de add-on, por ejemplo `blender_threadwell_addon/`.
- Implementar `__init__.py` instalable en Blender.
- Agregar panel `N Panel > Threadwell`.
- Permitir enviar prompts y mostrar respuesta.

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
