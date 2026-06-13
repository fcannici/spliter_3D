# Roadmap

## Fase 0 — Spike técnico

Objetivo: elegir backend boolean robusto.

Tareas:

- probar VTK boolean con cubo/cilindro/STL real;
- probar Manifold3D si está disponible;
- probar Blender headless;
- medir tiempos;
- documentar fallos.

Resultado esperado:

```txt
BooleanBackend elegido para MVP + fallback definido.
```

## Fase 1 — Core geométrico sin UI

Objetivo: librería testeable.

Tareas:

- crear paquete `split3r/geometry`;
- loaders STL/OBJ/3MF;
- validación de malla;
- cutter por plano;
- boolean intersection/difference;
- repair básico;
- export STL;
- tests con cube/cylinder.

Criterio de éxito:

```txt
pytest genera dos partes válidas desde un cubo cortado por plano.
```

## Fase 2 — UI mínima

Objetivo: app usable para plane cut.

Tareas:

- ventana Qt;
- viewport 3D;
- importar modelo;
- gizmo/plano simple;
- preview;
- apply split en worker;
- export.

Criterio de éxito:

```txt
Usuario puede partir un STL por plano desde la UI y exportar ambas partes.
```

## Fase 3 — Clearance/socket

Objetivo: negativos para FDM.

Tareas:

- clearance configurable;
- socket cutter;
- reporte de tolerancia;
- tests de volumen/bounds;
- presets: 0.1, 0.2, 0.3mm.

Criterio de éxito:

```txt
El resto contiene negativo con clearance y el slicer acepta ambos STL.
```

## Fase 4 — Box cut / region cut

Objetivo: soportar extracción de regiones tipo 1/8 de cubo.

Tareas:

- box cutter interactivo;
- intersection/difference por volumen;
- smart shell como selector auxiliar;
- boundary loop robusto;
- generar cutter desde boundary.

Criterio de éxito:

```txt
Se puede seleccionar/definir un octante y generar pieza + negativo.
```

## Fase 5 — Conectores paramétricos

Objetivo: que las partes encajen mejor.

Tareas:

- pins cilíndricos;
- sockets de pins con clearance;
- tabs/dovetails simples;
- orientación automática sobre plano de corte.

## Fase 6 — Release polish

Tareas:

- builds Windows/Linux;
- icons;
- logs por usuario;
- documentación;
- ejemplos pequeños;
- smoke test en slicers.

## Primera implementación recomendada actualizada

El feature central del producto es extraer inserts encastrables, por ejemplo un ojo de Deadpool para imprimirlo en otro color. Por eso el MVP debe empezar con:

```txt
Smart Region -> Boundary Loop -> Insert sólido con depth -> Slot cutter con clearance -> Boolean Difference -> Export body + insert
```

Luego agregar:

```txt
Box/Volume Cut + Clearance
```

Y después:

```txt
Plane Cut para dividir modelos grandes según volumen de impresora
```

Plane Cut sigue siendo importante, pero no es el chiste principal de la app.
