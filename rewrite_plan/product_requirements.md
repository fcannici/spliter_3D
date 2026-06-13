# Product Requirements

## Problema

La app actual permite seleccionar superficies y generar un plug/socket aproximado, pero es lenta, frágil y no produce cortes sólidos confiables en modelos reales.

La nueva app debe estar pensada desde el principio para dividir modelos 3D imprimibles por FDM.

## Usuario objetivo

Persona que tiene un modelo 3D grande o complejo y quiere partirlo en piezas imprimibles, con encastres o sockets para facilitar pegado/alineación.

## Casos de uso principales

### UC1 — Cortar por plano

1. Usuario carga un STL/3MF.
2. Inserta un plano de corte.
3. Mueve/rota el plano.
4. Previsualiza dos partes.
5. Configura clearance/socket.
6. Ejecuta corte.
7. Exporta piezas.

### UC2 — Cortar por región seleccionada

1. Usuario selecciona una zona de la superficie.
2. La app detecta boundary por adyacencia/ángulo o selección manual.
3. La app genera un volumen/cutter desde ese boundary.
4. Ejecuta boolean/intersection/difference.
5. Exporta pieza y cuerpo restante con negativo.

### UC3 — Crear encastres automáticos

1. Usuario elige tipo de encastre: socket simple, pins, dovetail, alignment tabs.
2. La app agrega geometría de encastre a la zona de corte.
3. Aplica clearance configurable.

## Requerimientos funcionales

- Importar STL, OBJ y 3MF.
- Mostrar modelo con navegación fluida.
- Seleccionar por:
  - plano de corte;
  - smart shell por normales;
  - pintura manual;
  - selección rectangular/lasso opcional.
- Generar sólidos cerrados para cada pieza.
- Aplicar boolean difference al original para generar socket/negativo.
- Clearance configurable en mm, default `0.2mm`.
- Exportar STL por pieza.
- Guardar proyecto en formato propio JSON + paths de assets o bundle.
- Undo/redo para operaciones destructivas.
- Mostrar reporte de validez de malla.

## Requerimientos no funcionales

- Windows y Linux soportados desde el día 1.
- Builds reproducibles con PyInstaller.
- UI no bloqueante durante operaciones pesadas.
- Operaciones cancelables.
- Logs legibles.
- Tests automatizados para geometría core.

## Métrica de éxito

- Un cubo puede partirse en 1/8 y 7/8 correctamente.
- Una figura STL manifold real puede partirse por plano y exportarse como dos STL válidos.
- El socket tiene clearance verificable respecto de la pieza.
- El slicer importa ambos STL sin reparación manual.
