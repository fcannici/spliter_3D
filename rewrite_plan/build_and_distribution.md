# Build and Distribution

## Plataformas objetivo

- Windows 10/11 x64.
- Linux x64, preferentemente Ubuntu 22.04+ compatible.

## Python recomendado

- Python 3.11 o 3.12.
- Evitar Python demasiado nuevo para releases, porque PyInstaller/VTK/PyVista pueden tardar en soportarlo.

## Dependencias separadas

```txt
requirements.txt          # runtime
requirements-dev.txt      # tests/lint
requirements-build.txt    # pyinstaller
requirements-optional.txt # blender/manifold extras si aplica
```

## Packaging

Usar PyInstaller con spec compartido y scripts por plataforma:

```txt
packaging/split3r.spec
scripts/build_linux.sh
scripts/build_windows.ps1
```

Regla importante:

```txt
Windows build se hace en Windows.
Linux build se hace en Linux.
```

## Linux Qt/VTK

VTK suele usar XOpenGL. En sesiones Wayland conviene forzar XCB/XWayland:

```py
if linux:
    QT_QPA_PLATFORM=xcb
```

Pero debe existir override:

```bash
SPLIT3R_QT_QPA_PLATFORM=wayland ./Split3r
```

## Backend Blender opcional

Si se usa Blender como backend boolean robusto, hay dos opciones:

### Opción A — Requerir Blender instalado

Pros:

- bundle más chico;
- menos licencias/packaging raro.

Contras:

- usuario debe instalar Blender.

### Opción B — Bundle con Blender embebido

Pros:

- experiencia cerrada.

Contras:

- build enorme;
- más complejo.

Recomendación inicial: detectar Blender instalado y usarlo si está disponible.

## CI opcional

GitHub Actions matrix:

```yaml
os: [windows-latest, ubuntu-22.04]
python: 3.11
steps:
  - install system deps linux
  - pip install requirements-build/dev
  - pytest
  - pyinstaller
  - upload artifact
```

## Validación de release

Antes de publicar:

- abrir app en Windows;
- abrir app en Linux X11/Wayland;
- importar STL simple;
- cortar cubo por plano;
- exportar partes;
- abrir partes en slicer;
- verificar que no requiere consola.

## Artefactos

Windows:

```txt
Split3r-x.y.z-windows-x64.zip
  Split3r/
    Split3r.exe
    _internal/
```

Linux:

```txt
Split3r-x.y.z-linux-x64.tar.gz
  Split3r/
    Split3r
    _internal/
```

Más adelante considerar AppImage.
