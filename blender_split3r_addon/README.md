# Split3r Blender Add-on Prototype

Prototipo V2 de Split3r usando Blender como motor geométrico.

## Por qué Blender

El prototipo PyVista/VTK demostró que la selección funciona, pero la generación manual de tapas, paredes y socket crea geometría incorrecta en modelos orgánicos complejos. Blender aporta:

- selección y edición de malla maduras;
- `Solidify` para dar espesor a una selección abierta;
- `Boolean EXACT` para crear el socket;
- inspección visual del cutter antes de aplicar;
- exportación STL desde el mismo entorno.

## Instalación manual

1. Abrir Blender.
2. `Edit > Preferences > Add-ons > Install...`
3. Seleccionar la carpeta comprimida del add-on o instalar este directorio como add-on de desarrollo.
4. Activar **Split3r Blender Prototype**.
5. En la vista 3D abrir el panel lateral con `N` y entrar a la pestaña **Split3r**.

## Flujo inicial

1. Usar **Import 3MF** desde el panel Split3r para cargar un `.3mf`/Bambu project. Opcionalmente activar **Save STL copy** para guardar una copia STL junto al `.3mf`.
2. Seleccionar el objeto importado.
3. Entrar a `Edit Mode` y seleccionar una cara semilla.
4. Usar **Smart Shell Select** con `Smart angle` y `Step angle`. `Smart angle` limita contra la normal inicial y `Step angle` limita cada salto entre caras; esto evita que seleccione toda la miniatura por curvatura gradual.
5. Usar **Create Plug + Socket**.
6. Por defecto el boolean no se aplica inmediatamente: se crea un modifier en el body y un cutter visible en modo wire para inspeccionar.
7. Si el resultado se ve correcto, aplicar el modifier o activar `Apply boolean`.
8. Exportar plug/body como STL.

## Puente Threadwell / pruebas asistidas

El panel incluye una sección **Threadwell Test Request**:

1. Elegir el archivo en **Test file** o con **Pick Test File**.
2. Escribir instrucciones en **Prompt**.
3. Presionar **Send Request to Threadwell**.

Esto guarda un JSON en:

```txt
%USERPROFILE%\split3r_blender_request.json
```

Threadwell puede leer ese request y ejecutar el smoke test headless:

```powershell
"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" --background --factory-startup --python scripts\blender_split3r_smoke_test.py -- "$env:USERPROFILE\split3r_blender_request.json"
```

El reporte se escribe al lado como `split3r_blender_request.report.json`.

## Estado

Este add-on es un prototipo inicial. La intención es reemplazar el core de extracción manual de la app PyVista por operaciones robustas de Blender.
