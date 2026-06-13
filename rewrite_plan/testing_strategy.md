# Testing Strategy

## Objetivo

Evitar repetir el problema actual: que “parece funcionar” visualmente pero genera geometría mala.

## Niveles de test

### Unit tests geometry

Sin Qt, rápidos.

Casos:

- cargar malla triangular;
- validar malla vacía;
- detectar non-watertight;
- boundary loop de selección simple;
- cutter por plano;
- boolean cube split;
- clearance aplicado correctamente.

### Golden mesh tests

Usar fixtures pequeñas en `tests/fixtures/`:

- cube.stl;
- cylinder.stl;
- sphere_lowpoly.stl;
- non_manifold_bad.stl.

Validar:

```txt
part_a.volume + part_b.volume ~= original.volume ± tolerancia
partes watertight
caras > 0
bounds esperados
```

Con clearance, el volumen total puede cambiar, pero debe ser explicable.

### Integration tests backend

Para cada backend disponible:

```py
backend.difference(cube, cutter)
backend.intersection(cube, cutter)
```

Si backend no está instalado, skip.

### UI smoke tests

Mínimo:

- importar app sin crash;
- crear ventana en entorno con display;
- comandos básicos no tiran excepción.

No intentar testear toda la interacción 3D al principio.

## Test manual obligatorio para release

Checklist:

1. Build Windows.
2. Build Linux.
3. Abrir app.
4. Importar cubo.
5. Plane cut al medio.
6. Exportar dos STL.
7. Abrir en slicer.
8. Repetir con un STL real.
9. Confirmar logs sin errores críticos.

## Métricas geométricas útiles

- `is_watertight`.
- volumen.
- número de shells conectados.
- self-intersections si backend lo permite.
- cantidad de agujeros/boundary edges.
- normales orientadas.

## Performance benchmarks

Guardar modelos de referencia:

- small: < 10k tris.
- medium: 100k tris.
- large: 1M tris.

Medir:

- tiempo de import;
- tiempo de preview;
- tiempo de boolean;
- memoria pico.

## Política

No mergear cambios de geometría sin tests sobre cubo/cilindro como mínimo.
