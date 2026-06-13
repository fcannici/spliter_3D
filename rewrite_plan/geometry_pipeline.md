# Geometry Pipeline

## Pipeline de importación

```txt
file -> loader -> triangulate -> normalize orientation -> validate -> scene mesh
```

Validaciones:

- tiene vértices y caras;
- caras trianguladas;
- no hay NaN/Inf;
- no hay caras degeneradas;
- normales coherentes;
- watertight si se requiere boolean sólido;
- volumen no cero;
- escala/unidades razonables.

## Pipeline de corte recomendado

### Corte por plano

El corte por plano debe ser el modo base porque es determinístico y robusto.

```txt
original
  -> crear halfspace/caja cutter A
  -> crear halfspace/caja cutter B
  -> part_a = intersection(original, cutter_a)
  -> part_b_raw = intersection(original, cutter_b)
  -> clearance_cutter = offset(part_a_boundary_or_connector, clearance)
  -> part_b = difference(part_b_raw, clearance_cutter)
  -> repair(part_a), repair(part_b)
```

Para empezar, incluso puede ser:

```txt
part_a = original ∩ cutter
part_b = original - offset(cutter, clearance)
```

Pero para sockets locales conviene que el clearance afecte solo zona de encastre, no toda la mitad.

### Corte por región superficial

```txt
selected_faces
  -> boundary_loop
  -> fit/local cut surface
  -> build cutter solid
  -> part = original ∩ cutter
  -> socket = original - offset(cutter, clearance)
```

## Boundary loop

Si hay selección de caras, el boundary se calcula por aristas compartidas:

```txt
edge pertenece al boundary si aparece en exactamente una cara seleccionada
```

Esto es mejor que depender solo de feature edges de VTK.

Pseudo:

```py
selected = set(face_ids)
edge_count = Counter()
for face in selected:
    for edge in face_edges(face):
        edge_count[sorted(edge)] += 1
boundary_edges = [e for e, count in edge_count.items() if count == 1]
loops = chain_edges_into_loops(boundary_edges)
```

Luego se valida:

- debe haber al menos un loop cerrado;
- no debe haber ramificaciones;
- si hay múltiples loops, tratarlos como agujeros o pedir confirmación.

## Clearance

Clearance FDM no debe ser solo mover puntos por normales sin control. Opciones:

1. Offset del cutter volumétrico.
2. Offset de superficie usando signed distance field.
3. Escalado local alrededor del centro del cutter, menos preciso.

Recomendación inicial:

- Para corte por plano: generar socket con geometría paramétrica simple y aplicar clearance en esa geometría.
- Para región superficial: usar signed distance/remesh cuando esté disponible.

## Reparación

Después de boolean:

```txt
remove duplicate vertices
remove degenerate faces
fill small holes opcional
recompute normals
triangulate
check watertight
```

Si no es watertight, mostrar advertencia antes de exportar.

## Export

- STL binario por default.
- 3MF opcional para múltiples piezas.
- Preservar unidades en metadatos cuando sea posible.
