# UI/UX Plan

## Objetivo UX

La app debe sentirse como herramienta de preparación para impresión, no como visor experimental.

## Layout

```txt
+---------------------------------------------------+
| Menu / Toolbar                                    |
+------------------------------+--------------------+
|                              | Import             |
|         3D Viewport          | Cut Mode           |
|                              | Clearance          |
|                              | Preview/Apply      |
|                              | Parts              |
|                              | Validation         |
+------------------------------+--------------------+
| Status / progress / logs                          |
+---------------------------------------------------+
```

## Toolbar principal

- Import Model
- Plane Cut
- Box Cut
- Smart Region
- Preview Split
- Apply Split
- Export Parts
- Undo/Redo

## Panel Cut Settings

Campos:

- Cut mode.
- Clearance mm, default `0.2`.
- Boolean backend: Auto/Blender/Manifold/VTK.
- Repair after boolean: yes/no.
- Keep original: yes/no.

## Viewport

Debe soportar:

- orbit/pan/zoom;
- selección clara;
- overlays de cutter;
- preview de partes con colores distintos;
- transparencia del cutter;
- ejes y grid opcionales.

## Feedback necesario

Durante boolean:

```txt
Computing split... [cancel]
```

Después:

```txt
Part A: watertight yes, volume 123.4mm³
Part B: watertight yes, volume 456.7mm³
Clearance: 0.2mm
```

Si falla:

```txt
Boolean failed with VTK backend.
Try Blender backend or repair mesh first.
```

## Flujo MVP recomendado

1. Abrir app.
2. Importar STL.
3. Click “Plane Cut”.
4. Aparece plano en centro del modelo.
5. Usuario mueve/rota plano.
6. Click “Preview”.
7. App muestra dos colores.
8. Usuario ajusta clearance.
9. Click “Apply”.
10. App genera partes en lista.
11. Export Parts.

## No hacer en MVP

- Pintura avanzada como feature central.
- Move mode de piezas sin persistencia real.
- Edición libre tipo CAD.
- Reparación mágica sin informar al usuario.

## Atajos sugeridos

- `Ctrl+O`: importar.
- `Ctrl+E`: exportar.
- `Ctrl+Z`: undo.
- `P`: plane cut.
- `B`: box cut.
- `Space`: preview/apply según contexto.

## Performance UX

- Nunca bloquear UI más de 200ms.
- Preview puede usar mesh decimado.
- Boolean final usa mesh completo.
- Mostrar progress aunque sea indeterminado.
