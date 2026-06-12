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

```bash
python -m venv venv
venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

Luego usa **Archivo > Importar STL/OBJ/3MF...** para cargar un modelo.

## Controles básicos

- Click derecho: pintar/seleccionar sobre la malla.
- `Ctrl + click derecho`: borrar selección.
- `Ctrl + rueda`: cambiar tamaño de brocha o tolerancia del Smart Shell.
- `EXTRACT PLUG & SOCKET`: crear plug y socket desde la selección.
- `Undo Last Extraction`: revertir la última extracción.
- `Archivo > Exportar último plug...`: guardar la pieza extraída.
- `Archivo > Exportar body/socket...`: guardar la malla restante.

## Scripts auxiliares

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
python -m py_compile main.py app/*.py scripts/*.py
pytest
```

## Política de assets grandes

Los modelos grandes (`*.stl`, `*.3mf`) están ignorados por defecto en `.gitignore`. Para ejemplos pequeños, usar `assets/`; para modelos pesados, preferir Git LFS o almacenamiento externo.

## Estado

Proyecto en refactor inicial. La lógica nueva se está separando en módulos dentro de `app/`, mientras `main.py` mantiene la interfaz Qt principal.
