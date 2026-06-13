# Split3r Rewrite Plan

Plan para reimplementar la app desde cero manteniendo el concepto: partir modelos 3D para impresión FDM generando piezas sólidas encastrables con tolerancia configurable.

## Objetivo del producto

Crear una app desktop Python para Windows y Linux que permita:

1. Importar STL/OBJ/3MF.
2. Visualizar el modelo de forma fluida.
3. Definir una región/corte de separación.
4. Generar dos o más sólidos imprimibles.
5. Crear negativos/sockets con clearance, por ejemplo `0.2mm`.
6. Exportar STL/3MF listos para slicer.

## Principio clave

La app nueva no debe depender de “extruir caras seleccionadas” como operación principal. Ese enfoque es frágil.

El núcleo correcto debe ser:

```txt
original_mesh -> cutter_volume -> boolean/intersection/difference -> repair -> export
```

Para cada separación:

```txt
pieza_extraida = original ∩ volumen_de_corte
socket_cutter = offset(pieza_extraida o cutter, clearance)
resto = original - socket_cutter
```

## Documentos

- `product_requirements.md`: qué tiene que hacer la app.
- `architecture.md`: arquitectura propuesta.
- `geometry_pipeline.md`: pipeline geométrico robusto.
- `selection_and_cutting.md`: cómo definir boundaries/cutters.
- `interlocking_insert_workflow.md`: flujo principal de inserts/machos con slot/negativo y clearance FDM.
- `ui_ux.md`: experiencia de usuario propuesta.
- `build_and_distribution.md`: builds Windows/Linux.
- `testing_strategy.md`: tests y validación.
- `roadmap.md`: fases de implementación.

## Stack recomendado

- UI: PySide6 o PyQt6.
- Visualización 3D: VTK directo o PyVistaQt con wrapper propio.
- Mesh IO: trimesh + meshio/pyvista según formato.
- Geometría robusta:
  - primera opción: Blender Python headless como backend boolean opcional/local;
  - segunda opción: Manifold3D/trimesh boolean si está disponible;
  - fallback: VTK boolean con validación fuerte.
- Packaging: PyInstaller con scripts por plataforma.

## Decisión importante

El modo central de la app debe ser **Interlocking Insert**: seleccionar una región visible del modelo, convertirla en un macho sólido con profundidad configurable, y restar un slot/negativo con clearance del cuerpo original. Los plane cuts son importantes, pero vienen después para dividir modelos grandes según volumen de impresora.

Para que sea confiable para FDM, hay que priorizar operaciones booleanas sobre sólidos cerrados y validación manifold. La selección de caras puede seguir existiendo, pero debe ser solo una forma de crear el insert/cutter, no el mecanismo final de generación de piezas.
