# Architecture

## Principio

Separar completamente UI, dominio geométrico, backend booleano, import/export y packaging.

```txt
split3r/
  app.py                    # entrypoint
  ui/
    main_window.py
    viewport.py
    panels.py
    commands.py
  core/
    document.py             # estado del proyecto
    operations.py           # comandos undo/redo
    units.py
  geometry/
    mesh.py                 # tipos internos
    io.py                   # import/export
    validation.py
    selection.py
    cutters.py
    booleans.py
    repair.py
    offsets.py
  workers/
    task_runner.py          # background jobs
  platform/
    paths.py
    logging.py
packaging/
  split3r.spec
scripts/
  build_linux.sh
  build_windows.ps1
tests/
```

## Capas

### UI

Responsable solo de:

- mostrar modelo;
- recibir input;
- disparar comandos;
- mostrar progreso/errores.

No debe calcular booleanos ni manipular meshes directamente salvo para previsualización.

### Core/document

Mantiene estado:

```py
Document:
    original_mesh
    current_parts
    operations_history
    selection_state
    cut_settings
```

### Geometry

Debe ser testeable sin Qt.

Funciones puras o casi puras:

```py
load_mesh(path) -> MeshModel
validate_mesh(mesh) -> ValidationReport
create_plane_cutter(mesh, plane, margin) -> Solid
boolean_intersection(a, b) -> Mesh
boolean_difference(a, b) -> Mesh
apply_clearance(mesh_or_cutter, amount) -> Mesh
repair_mesh(mesh) -> Mesh
```

### Workers

Booleanos y reparaciones pueden tardar. Deben correr en threads/processes:

```txt
UI -> enqueue operation -> progress -> result/error -> document update
```

## Modelo de datos recomendado

```py
@dataclass
class MeshModel:
    id: str
    name: str
    vertices: np.ndarray
    faces: np.ndarray
    transform: np.ndarray
    source_path: Path | None
    metadata: dict

@dataclass
class CutSettings:
    mode: Literal['plane', 'surface_region', 'box', 'custom_cutter']
    clearance_mm: float = 0.2
    repair: bool = True
    boolean_backend: str = 'auto'
```

## Backends booleanos

Diseñar interfaz:

```py
class BooleanBackend:
    def difference(self, a, b): ...
    def intersection(self, a, b): ...
    def union(self, a, b): ...
    def is_available(self): ...
```

Implementaciones posibles:

1. `BlenderBackend`: robusto, externo/headless.
2. `ManifoldBackend`: rápido y robusto si disponible.
3. `VTKBackend`: disponible con PyVista/VTK, fallback.
4. `TrimeshBackend`: wrapper sobre backends instalados.

## Por qué backend externo opcional

Los booleanos 3D robustos son difíciles. VTK/trimesh pueden fallar con mallas reales. Blender o Manifold3D suelen ser más confiables para este tipo de workflow.
