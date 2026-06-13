# Selection and Cutting Model

## Problema con la app actual

La selección actual por smart shell identifica superficies, pero no define por sí sola un volumen sólido de corte. Para FDM necesitamos cortar volumen, no solo superficies.

## Modos de corte propuestos

### 1. Plane Cut MVP

Modo principal para la primera versión nueva.

UI:

- plano visible;
- gizmo para mover/rotar;
- botón “Preview Split”;
- botón “Apply Split”.

Ventajas:

- robusto;
- fácil de explicar;
- fácil de testear;
- cubre el caso principal de partir modelos grandes.

### 2. Box/Volume Cut

Usuario coloca una caja o volumen paramétrico.

```txt
part = original ∩ box
rest = original - offset(box, clearance)
```

Útil para “quiero sacar este octante/parte”.

### 3. Smart Surface Region

Selección por normales/ángulo, pero con otro objetivo:

1. seleccionar caras;
2. calcular boundary loop;
3. crear cutter desde ese boundary;
4. cortar booleanamente.

La selección no debe generar la pieza directamente.

## Smart shell

Mantener algoritmo:

```txt
flood fill sobre caras adyacentes si angle_between_normals <= threshold
```

Pero agregar:

- límite de cantidad de caras;
- cache de adyacencia;
- preview decimado;
- ejecución en worker si es grande.

## Boundary robusto

No depender de `extract_feature_edges` como fuente primaria.

Calcular boundary en arrays propios:

```py
selected_faces -> selected_edges -> edges_con_count_1 -> loops
```

Errores que la UI debe mostrar:

- selección sin boundary;
- boundary abierto;
- boundary con ramas;
- múltiples loops no soportados todavía;
- selección demasiado chica.

## Creación de cutter desde boundary

Opciones:

### A. Extruded boundary cutter

- proyectar boundary a plano local;
- crear polígono 2D;
- extruir hacia adentro/afuera;
- boolean.

### B. Surface patch thickening

- tomar selected surface;
- offset hacia adentro/afuera;
- crear paredes laterales;
- usar como cutter.

Es parecido a lo actual, pero debe ser cutter booleano, no resultado final.

### C. User-guided volume

Para casos complejos, permitir usar caja/cilindro/plano en vez de inferir todo.

## Recomendación MVP

No arrancar con smart surface como modo principal.

Orden sugerido:

1. Plane cut robusto.
2. Box cut robusto.
3. Agregar conectores/sockets paramétricos.
4. Recién después smart shell -> cutter.

Esto evita repetir el problema actual: mucha magia de selección, poca robustez geométrica.
