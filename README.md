# Split3r Clone

Split3r Clone es una aplicación experimental en Python para cargar modelos 3D (`.stl`, `.obj`, `.3mf`), seleccionar regiones sobre la malla y generar **interlocking inserts**: una pieza macho imprimible por separado y el slot/negativo correspondiente en el cuerpo original para flujos FDM multicolor o por partes.

## Funcionalidades

- Carga de modelos STL/OBJ/3MF con PyVista, VTK y Trimesh.
- Selección por `Smart Shell` basada en adyacencia y ángulo entre caras.
- Selección manual con brocha esférica.
- Extracción de insert macho sólido con profundidad configurable.
- Generación de slot/negativo en el cuerpo original con clearance FDM configurable, default `0.2mm`.
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

```bash
python main.py
```

Luego usa **Archivo > Importar STL/OBJ/3MF...** para cargar un modelo.

## Controles básicos

- Click derecho: pintar/seleccionar sobre la malla.
- `Ctrl + click derecho`: borrar selección.
- `Ctrl + rueda`: cambiar tamaño de brocha o tolerancia del Smart Shell.
- `EXTRACT INTERLOCKING INSERT`: crear el insert macho y restar el slot al cuerpo original.
- `Undo Last Extraction`: revertir la última extracción.
- `Archivo > Exportar último plug...`: guardar la pieza extraída.
- `Archivo > Exportar body/socket...`: guardar la malla restante.

## Workflow principal: interlocking insert

1. Importá un modelo.
2. Seleccioná una región superficial, por ejemplo un ojo/emblema/panel.
3. Ajustá `Grosor de Pieza` para definir el `depth` del macho hacia adentro.
4. Ajustá `Buffer socket` para la tolerancia FDM. El default es `0.2mm`.
5. Ejecutá `EXTRACT INTERLOCKING INSERT`.
6. Exportá el último insert y el body/socket desde el menú Archivo.

La operación intenta hacer un boolean real del slot sobre el cuerpo original. Si un backend robusto como Blender está disponible en `PATH`, la app puede usarlo; si no, usa VTK/PyVista y deja warnings en `app_log.txt` si debe caer a fallback.

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

## Estado

Proyecto en refactor inicial. La lógica nueva se está separando en módulos dentro de `app/`, mientras `main.py` mantiene la interfaz Qt principal.
