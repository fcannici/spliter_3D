# Interlocking Insert Workflow

Este es el flujo clave de la app: extraer una región superficial del modelo para imprimirla como pieza separada/color separado, y generar automáticamente el slot/negativo en el cuerpo original con clearance FDM.

## Ejemplo mental

Modelo: máscara/cabeza de Deadpool.

Usuario selecciona el ojo.

La app debe generar:

1. **Insert / macho**: la geometría del ojo, con volumen hacia adentro para ser imprimible como pieza separada.
2. **Body / hembra / slot**: la máscara original con un hueco donde entra ese insert.
3. **Clearance**: el slot debe ser más grande que el macho, por ejemplo `0.2mm`, para tolerancia FDM.
4. **Depth configurable**: el usuario define cuánto se mete el macho dentro del cuerpo, por ejemplo `2mm`, `3mm`, `5mm`.

## No es un corte plano

Este workflow no es principalmente `plane cut`. Es un modo tipo:

```txt
Smart Surface Insert / Interlocking Insert
```

Plane cut es otro feature futuro para dividir modelos grandes según volumen de impresora.

## Resultado esperado

Si el usuario selecciona una superficie coloreada o una isla geométrica, por ejemplo un ojo:

```txt
selected_surface = región del ojo
boundary_loop = borde cerrado del ojo
insert_top = superficie exterior visible del ojo
insert_body = volumen extruido hacia adentro según depth
slot_cutter = insert_body expandido con clearance
body_with_slot = original - slot_cutter
```

Exportables:

```txt
Deadpool_body_with_eye_slot.stl
Deadpool_eye_insert.stl
```

## Parámetros mínimos

- `depth_mm`: profundidad del macho hacia adentro. Default sugerido: `3.0mm`.
- `clearance_mm`: tolerancia del slot. Default sugerido: `0.2mm`.
- `draft_angle_deg`: opcional, leve conicidad para que encastre mejor. Default: `0°` o `1°`.
- `lip/flush mode`: si la cara exterior queda exactamente flush con el original.
- `normal mode`: dirección de extrusión:
  - por normales promedio;
  - por normales por vértice;
  - por dirección manual.

## Algoritmo conceptual

### 1. Selección

El usuario elige la región visible:

- smart shell por normales/ángulo;
- selección por material/color si el archivo lo tiene;
- pintura manual para corregir;
- lasso opcional.

### 2. Boundary robusto

Calcular boundary por conectividad de triángulos, no por heurísticas visuales:

```py
selected_faces = set(...)
boundary_edges = edges_used_by_exactly_one_selected_face(selected_faces)
boundary_loops = chain_edges(boundary_edges)
```

Validar:

- debe haber loop cerrado;
- no debe haber ramas;
- si hay múltiples loops, pedir confirmación o soportar agujeros.

### 3. Crear insert macho

Crear un sólido cerrado:

```txt
top_surface = selected surface original
bottom_surface = top_surface offset inward by depth
side_walls = ruled surface between boundary_top and boundary_bottom
insert = top + bottom + walls
```

Importante: el insert debe preservar la superficie exterior original para que al colocarlo quede visualmente integrado.

### 4. Crear cutter del slot

El slot no debe ser igual al insert. Debe ser el insert expandido:

```txt
slot_cutter = offset(insert, clearance_mm)
```

Si offset volumétrico robusto no está disponible al principio, aproximación MVP:

- mover paredes laterales hacia afuera en plano local por `clearance`;
- mover bottom más profundo por `clearance`;
- mantener abertura exterior con clearance lateral.

### 5. Boolean sobre original

```txt
body_with_slot = original - slot_cutter
```

Si el boolean falla:

- intentar backend alternativo;
- reparar mallas;
- mostrar error claro;
- no exportar geometría dudosa como si estuviera bien.

## Diferencia con la app actual

La app actual intenta construir plug/socket desde caras seleccionadas y pegar superficies. Eso puede parecer visualmente correcto pero no garantiza un sólido booleano confiable.

La app nueva debe tratar el insert como un **sólido real** y el slot como una **resta booleana real** sobre el cuerpo original.

## MVP específico para este workflow

Antes de plane cuts, se puede construir un MVP centrado en inserts:

1. Importar STL.
2. Smart-select una región tipo ojo.
3. Calcular boundary.
4. Generar insert con depth fijo/configurable.
5. Generar slot cutter con `0.2mm`.
6. Boolean difference sobre original.
7. Exportar body + insert.

## Riesgos técnicos

- Offsets 3D robustos son difíciles.
- Boolean con mallas no-manifold puede fallar.
- Dirección de extrusión por normales puede producir autointersecciones en superficies muy curvas.
- Boundaries ruidosos de STL escaneados o triangulados irregularmente pueden necesitar smoothing/simplificación.

## Decisión recomendada

Para este feature, priorizar un backend boolean robusto:

1. Blender headless como backend confiable.
2. Manifold3D si soporta el caso y está disponible.
3. VTK/PyVista solo como fallback o preview.

## Validación con fixture

Crear fixtures específicas:

- `eye_patch_on_mask.stl` o mock equivalente.
- `colored_insert_region.3mf` si hay materiales.
- `curved_surface_patch.stl`.

Tests esperados:

```txt
insert is watertight
body_with_slot is watertight or reports repair needed
slot volume > insert volume
clearance approx 0.2mm on side walls
insert exterior surface matches original selected surface
```
