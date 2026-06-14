# Split3r Clone

Split3r Clone es una aplicación experimental en Python para cargar modelos 3D (`.stl`, `.obj`, `.3mf`), seleccionar caras sobre la malla y extraer una pieza tipo **plug & socket** pensada para flujos de impresión 3D.

## Funcionalidades

- Carga de modelos STL/OBJ/3MF con PyVista, VTK y Trimesh.
- Selección por `Smart Shell` basada en adyacencia y ángulo entre caras.
- Selección manual con brocha esférica.
- Extracción de una pieza sólida y cavidad socket.
- Modo de movimiento para arrastrar piezas extraídas.
- Exportación del último plug y del body/socket.
- Undo de la última extracción.

## Instalación

Windows PowerShell:

```powershell
python -m venv venv
. .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

Prototipo clásico PyVista/VTK:

```bash
python main.py
```

Split3r V2 standalone Smart Paint:

```bash
python standalone_main.py
```

Luego usa **Archivo > Importar STL/OBJ/3MF...** / **Archivo > Importar modelo...** para cargar un modelo.

## Controles básicos

- Click derecho: pintar/seleccionar sobre la malla.
- `Ctrl + click derecho`: borrar selección.
- `Ctrl + rueda`: cambiar tamaño de brocha o tolerancia del Smart Shell.
- `EXTRACT PLUG & SOCKET`: crear plug y socket desde la selección.
- `Undo Last Extraction`: revertir la última extracción.
- `Archivo > Exportar último plug...`: guardar la pieza extraída.
- `Archivo > Exportar body/socket...`: guardar la malla restante.

## Builds de escritorio

La repo incluye empaquetado con PyInstaller para generar bundles nativos por plataforma desde la misma base de código.

> Importante: los builds deben correrse en la plataforma destino. Para generar `.exe`, correr el build en Windows; para generar el binario Linux, correrlo en Linux. Se recomienda Python 3.11 o 3.12 para builds reproducibles con PyInstaller/PyVista/VTK.

Linux:

```bash
./scripts/build_linux.sh
```

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Cada script crea un entorno `.venv-build/`, instala `requirements-build.txt`, valida sintaxis y ejecuta PyInstaller con `packaging/split3r.spec`.

Los artefactos quedan en:

```txt
dist/Split3rClone/
```

En Windows, el ejecutable queda dentro de esa carpeta como `Split3rClone.exe`. En Linux, queda como `Split3rClone`.

También hay un workflow opcional en `.github/workflows/build.yml` para validar/generar ambos artefactos en CI.

## Scripts auxiliares

Las dependencias de estos scripts son opcionales:

```bash
pip install -r requirements-scripts.txt
```

Extraer frames:

```bash
python scripts/extract_frames.py --video ruta/video.mp4 --out frames
```

Extraer 11 frames distribuidos de 0% a 100%:

```bash
python scripts/extract_more.py --video ruta/video.mp4 --out frames_more
```

Transcribir audio de un video:

```bash
python scripts/transcribe.py --video ruta/video.mp4 --audio audio.wav --language es-ES
```

## Tests y validación ligera

```bash
pip install -r requirements-dev.txt
python -m compileall -q main.py app scripts tests
pytest
```

## Política de assets grandes

Los modelos grandes (`*.stl`, `*.3mf`) están ignorados por defecto en `.gitignore`. Para ejemplos pequeños, usar `assets/`; para modelos pesados, preferir Git LFS o almacenamiento externo.

## Split3r V2 standalone Smart Paint

La ruta recomendada de producto es una app separada en:

```txt
split3r_standalone/
```

Objetivo UX: aproximarse al flujo de Split3r/Bambu Paint:

- Click/arrastrar pinta caras con brocha.
- Slider `Brush radius` controla el radio de pintura.
- `Ctrl + Click` marca Include/pieza en rojo.
- `Alt + Click` marca Exclude/proteger body en azul.
- `Smart Paint Expand` expande desde semillas positivas sin entrar en zonas protegidas.
- El backend de extracción robusta seguirá usando Blender headless en una fase posterior.

Entrypoint:

```bash
python standalone_main.py
```

## Blender add-on prototype

Después de probar el core PyVista/VTK con modelos orgánicos complejos, se inició una V2 recomendada como add-on de Blender en:

```txt
blender_split3r_addon/
```

Incluye un panel `N Panel > Split3r` con:

- Smart Shell Select usando `bmesh`.
- Create Plug + Socket usando `Solidify` y `Boolean EXACT`.
- Exportación STL de objetos seleccionados.

Ver `blender_split3r_addon/README.md` para instalación y flujo de prueba.

## Estado

La app PyVista queda como prototipo/reference. El add-on de Blender queda como laboratorio geométrico. El camino recomendado para producto final es `split3r_standalone/` con Blender headless como motor interno para boolean/solidify/export.
