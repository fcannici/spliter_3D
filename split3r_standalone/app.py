from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt6")
os.environ.setdefault("QT_OPENGL", "desktop")

import numpy as np
import pyvista as pv
import vtk
from scipy.spatial import KDTree
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from app.extraction import extract_plug_socket
from app.mesh_io import load_trimesh, trimesh_to_polydata, validate_polydata
from app.selection import build_adjacency_dict
from split3r_standalone.selection import PaintSelectionState, SmartPaintParams, smart_paint_expand

LOG_PATH = Path("split3r_standalone.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("split3r_standalone")

BASE_COLOR = np.array([188, 184, 150], dtype=np.uint8)
INCLUDE_COLOR = np.array([220, 38, 38], dtype=np.uint8)
EXCLUDE_COLOR = np.array([30, 95, 220], dtype=np.uint8)


class PaintInteractor(QtInteractor):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.main_window: Split3rStandalone | None = parent
        self.setMouseTracking(True)
        self.is_painting = False
        self.paint_mode = "include"

    def _mode_from_event(self, ev) -> str:
        modifiers = ev.modifiers()
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return "exclude"
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return "include"
        return self.main_window.current_paint_mode() if self.main_window is not None else "include"

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.main_window is not None:
            self.is_painting = True
            self.paint_mode = self._mode_from_event(ev)
            vtk_pos = (ev.pos().x(), self.height() - ev.pos().y())
            self.main_window.paint_at(vtk_pos, mode=self.paint_mode)
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.is_painting and self.main_window is not None:
            vtk_pos = (ev.pos().x(), self.height() - ev.pos().y())
            self.main_window.paint_at(vtk_pos, mode=self.paint_mode)
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.is_painting:
            self.is_painting = False
            return
        super().mouseReleaseEvent(ev)


class Split3rStandalone(QMainWindow):
    """Standalone Split3r V2 shell.

    This is the product-style UI path: Blender remains useful as a headless geometry engine,
    but selection/paining UX is owned by this app instead of Blender edit mode.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Split3r V2 - Smart Paint")
        self.resize(1280, 820)

        self.current_mesh: pv.PolyData | None = None
        self.trimesh_mesh = None
        self.adjacency: dict[int, list[tuple[int, float]]] = {}
        self.paint_state = PaintSelectionState()
        self.cell_picker = vtk.vtkCellPicker()
        self.main_actor = None
        self.plug_actor = None
        self.body_actor = None
        self.cell_centers: np.ndarray | None = None
        self.cell_normals: np.ndarray | None = None
        self.cell_center_tree: KDTree | None = None
        self.last_pick_position: np.ndarray | None = None
        self.last_plug: pv.PolyData | None = None
        self.last_body: pv.PolyData | None = None

        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QHBoxLayout(self.central)
        self.plotter = PaintInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("#202020")
        self.plotter.add_axes()
        self.plotter.enable_terrain_style()

        self._build_menu()
        self._build_panel()
        self.status_label.setText("Listo. Importá un STL/OBJ/3MF para empezar.")
        logger.info("Standalone app started")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        import_action = QAction("Importar modelo...", self)
        import_action.setShortcut("Ctrl+O")
        import_action.triggered.connect(self.import_model)
        file_menu.addAction(import_action)

        exit_action = QAction("Salir", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _build_panel(self) -> None:
        self.dock = QDockWidget("Split3r Smart Paint", self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        panel = QWidget()
        self.dock.setWidget(panel)
        panel_layout = QVBoxLayout(panel)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("background:#333;color:white;padding:6px;font-family:monospace")
        panel_layout.addWidget(self.status_label)

        self.count_label = QLabel("Include: 0 | Exclude: 0")
        panel_layout.addWidget(self.count_label)

        paint_group = QGroupBox("1) Paint")
        paint_layout = QVBoxLayout(paint_group)
        self.mode_group = QButtonGroup(self)
        self.include_radio = QRadioButton("Include / pieza (rojo)")
        self.exclude_radio = QRadioButton("Exclude / proteger body (azul)")
        self.erase_radio = QRadioButton("Erase marks")
        self.include_radio.setChecked(True)
        for btn in (self.include_radio, self.exclude_radio, self.erase_radio):
            self.mode_group.addButton(btn)
            paint_layout.addWidget(btn)
        paint_layout.addWidget(QLabel("Click/arrastrar pinta. Ctrl+Click Include. Alt+Click Exclude."))
        self.brush_label = QLabel("Brush radius: 2.0")
        paint_layout.addWidget(self.brush_label)
        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setMinimum(1)
        self.brush_slider.setMaximum(100)
        self.brush_slider.setValue(20)
        self.brush_slider.valueChanged.connect(lambda v: self.brush_label.setText(f"Brush radius: {v / 10:.1f}"))
        paint_layout.addWidget(self.brush_slider)
        panel_layout.addWidget(paint_group)

        expand_group = QGroupBox("2) Smart Expand")
        expand_layout = QVBoxLayout(expand_group)
        self.angle_label = QLabel("Max angle: 22°")
        expand_layout.addWidget(self.angle_label)
        self.angle_slider = QSlider(Qt.Orientation.Horizontal)
        self.angle_slider.setMinimum(5)
        self.angle_slider.setMaximum(60)
        self.angle_slider.setValue(22)
        self.angle_slider.valueChanged.connect(lambda v: self.angle_label.setText(f"Max angle: {v}°"))
        expand_layout.addWidget(self.angle_slider)

        self.buffer_label = QLabel("Exclude buffer: 1 ring")
        expand_layout.addWidget(self.buffer_label)
        self.buffer_slider = QSlider(Qt.Orientation.Horizontal)
        self.buffer_slider.setMinimum(0)
        self.buffer_slider.setMaximum(5)
        self.buffer_slider.setValue(1)
        self.buffer_slider.valueChanged.connect(lambda v: self.buffer_label.setText(f"Exclude buffer: {v} ring(s)"))
        expand_layout.addWidget(self.buffer_slider)

        expand_btn = QPushButton("Smart Paint Expand")
        expand_btn.clicked.connect(self.smart_expand)
        expand_layout.addWidget(expand_btn)
        panel_layout.addWidget(expand_group)

        clear_btn = QPushButton("Clear Marks")
        clear_btn.clicked.connect(self.clear_marks)
        panel_layout.addWidget(clear_btn)

        extract_group = QGroupBox("3) Extract")
        extract_layout = QVBoxLayout(extract_group)
        self.depth_label = QLabel("Plug thickness: 2.0")
        extract_layout.addWidget(self.depth_label)
        self.depth_slider = QSlider(Qt.Orientation.Horizontal)
        self.depth_slider.setMinimum(1)
        self.depth_slider.setMaximum(100)
        self.depth_slider.setValue(20)
        self.depth_slider.valueChanged.connect(lambda v: self.depth_label.setText(f"Plug thickness: {v / 10:.1f}"))
        extract_layout.addWidget(self.depth_slider)
        self.preview_selected_btn = QPushButton("Preview Selected Piece")
        self.preview_selected_btn.clicked.connect(self.preview_selected_piece)
        extract_layout.addWidget(self.preview_selected_btn)
        self.export_selected_btn = QPushButton("Export Selected Piece STL")
        self.export_selected_btn.clicked.connect(self.export_selected_piece)
        extract_layout.addWidget(self.export_selected_btn)
        self.extract_btn = QPushButton("Extract Plug + Socket")
        self.extract_btn.clicked.connect(self.extract_selection)
        extract_layout.addWidget(self.extract_btn)
        self.export_btn = QPushButton("Export Last Plug + Body")
        self.export_btn.clicked.connect(self.export_last_outputs)
        self.export_btn.setEnabled(False)
        extract_layout.addWidget(self.export_btn)
        extract_layout.addWidget(QLabel("Extracción inicial local; Blender headless robusto queda para V2.1."))
        panel_layout.addWidget(extract_group)
        panel_layout.addStretch(1)

    def current_paint_mode(self) -> str:
        if self.exclude_radio.isChecked():
            return "exclude"
        if self.erase_radio.isChecked():
            return "erase"
        return "include"

    def import_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar modelo",
            "",
            "3D Mesh (*.stl *.obj *.3mf);;Todos (*.*)",
        )
        if path:
            self.load_model(path)

    def load_model(self, path: str | Path) -> None:
        try:
            self.trimesh_mesh = load_trimesh(path)
            self.current_mesh = trimesh_to_polydata(self.trimesh_mesh).triangulate()
            self.current_mesh = self.current_mesh.compute_normals(cell_normals=True, point_normals=False, auto_orient_normals=True)
            validate_polydata(self.current_mesh)
            self.adjacency = build_adjacency_dict(
                self.trimesh_mesh.face_adjacency,
                self.trimesh_mesh.face_adjacency_angles,
            )
            self.paint_state.clear()
            self.cell_centers = self.current_mesh.cell_centers().points
            self.cell_normals = np.asarray(self.current_mesh.cell_data.get("Normals"), dtype=float)
            self.cell_center_tree = KDTree(self.cell_centers)
            self.last_plug = None
            self.last_body = None
            self.export_btn.setEnabled(False)
            self.plotter.clear()
            self.plotter.add_axes()
            self.current_mesh.cell_data["split3r_color"] = self._cell_colors()
            self.main_actor = self.plotter.add_mesh(
                self.current_mesh,
                scalars="split3r_color",
                rgb=True,
                show_edges=False,
                smooth_shading=True,
            )
            self.plotter.reset_camera()
            self._update_labels()
            self.status_label.setText(f"Modelo cargado: {Path(path).name}\nFaces: {self.current_mesh.n_cells}")
            logger.info("Loaded model %s faces=%s", path, self.current_mesh.n_cells)
        except Exception as exc:  # noqa: BLE001 - UI boundary
            logger.exception("Import failed")
            self.status_label.setText(f"Error importando modelo: {exc}")

    def _pick_face(self, vtk_pos: tuple[int, int]) -> int:
        if self.current_mesh is None:
            return -1
        self.cell_picker.Pick(vtk_pos[0], vtk_pos[1], 0, self.plotter.renderer)
        cell_id = int(self.cell_picker.GetCellId())
        if cell_id >= 0:
            self.last_pick_position = np.asarray(self.cell_picker.GetPickPosition(), dtype=float)
        else:
            self.last_pick_position = None
        return cell_id

    def _brush_faces(self, seed_face: int) -> set[int]:
        if seed_face < 0:
            return set()
        if self.cell_centers is None or self.cell_center_tree is None:
            return {seed_face}
        radius = max(0.01, self.brush_slider.value() / 10.0)
        pick_position = self.last_pick_position if self.last_pick_position is not None else self.cell_centers[seed_face]
        nearby = self.cell_center_tree.query_ball_point(pick_position, r=radius)
        if not nearby:
            return {seed_face}

        # Bambu/Split3r-like paint should affect the visible shell under the cursor, not
        # back-side/internal triangles inside the brush sphere. Keep faces near the picked
        # surface depth and facing the active camera.
        camera_pos = np.asarray(self.plotter.renderer.GetActiveCamera().GetPosition(), dtype=float)
        view_vec = camera_pos - pick_position
        view_norm = float(np.linalg.norm(view_vec))
        if view_norm <= 1e-9 or self.cell_normals is None or len(self.cell_normals) != len(self.cell_centers):
            return {int(face_id) for face_id in nearby}
        view_dir = view_vec / view_norm
        max_depth = max(radius * 0.55, 0.05)
        visible_faces: set[int] = set()
        for face_id in nearby:
            face_id = int(face_id)
            center = self.cell_centers[face_id]
            depth_delta = float(np.dot(center - pick_position, view_dir))
            if abs(depth_delta) > max_depth:
                continue
            normal = self.cell_normals[face_id]
            if float(np.dot(normal, camera_pos - center)) <= 0:
                continue
            visible_faces.add(face_id)
        return visible_faces or {seed_face}

    def paint_at(self, vtk_pos: tuple[int, int], mode: str) -> None:
        face = self._pick_face(vtk_pos)
        faces = self._brush_faces(face)
        if not faces:
            return
        if mode == "exclude":
            self.paint_state.mark_exclude(faces)
        elif mode == "erase":
            self.paint_state.erase(faces)
        else:
            self.paint_state.mark_include(faces)
        self.refresh_colors()
        self._update_labels()

    def smart_expand(self) -> None:
        if self.current_mesh is None:
            self.status_label.setText("Primero importá un modelo.")
            return
        params = SmartPaintParams(
            max_angle_degrees=float(self.angle_slider.value()),
            exclude_buffer_rings=int(self.buffer_slider.value()),
        )
        before = len(self.paint_state.include_faces)
        smart_paint_expand(self.paint_state, self.adjacency, params)
        self.refresh_colors()
        self._update_labels()
        self.status_label.setText(f"Smart Expand: {before} → {len(self.paint_state.include_faces)} caras.")

    def clear_marks(self) -> None:
        self.paint_state.clear()
        self.refresh_colors()
        self._update_labels()
        self.status_label.setText("Marcas limpiadas.")

    def _cell_colors(self) -> np.ndarray:
        if self.current_mesh is None:
            return np.empty((0, 3), dtype=np.uint8)
        colors = np.tile(BASE_COLOR, (self.current_mesh.n_cells, 1))
        if self.paint_state.include_faces:
            idx = np.fromiter((i for i in self.paint_state.include_faces if 0 <= i < self.current_mesh.n_cells), dtype=np.int64)
            if idx.size:
                colors[idx] = INCLUDE_COLOR
        if self.paint_state.exclude_faces:
            idx = np.fromiter((i for i in self.paint_state.exclude_faces if 0 <= i < self.current_mesh.n_cells), dtype=np.int64)
            if idx.size:
                colors[idx] = EXCLUDE_COLOR
        return colors

    def refresh_colors(self) -> None:
        if self.current_mesh is None:
            return
        self.current_mesh.cell_data["split3r_color"] = self._cell_colors()
        self.plotter.update_scalars(self.current_mesh.cell_data["split3r_color"], mesh=self.current_mesh, render=True)

    def _selected_piece_surface(self) -> pv.PolyData:
        if self.current_mesh is None:
            raise ValueError("Primero importá un modelo.")
        if not self.paint_state.include_faces:
            raise ValueError("Pintá o expandí una selección roja antes de extraer.")
        valid = sorted(face for face in self.paint_state.include_faces if 0 <= face < self.current_mesh.n_cells)
        if not valid:
            raise ValueError("La selección no contiene caras válidas.")
        return self.current_mesh.extract_cells(valid).extract_surface().triangulate().clean()

    def preview_selected_piece(self) -> None:
        try:
            piece = self._selected_piece_surface()
            if self.plug_actor is not None:
                self.plotter.remove_actor(self.plug_actor)
            self.plug_actor = self.plotter.add_mesh(piece, color="#d98613", opacity=1.0, show_edges=False)
            self.plotter.render()
            self.status_label.setText(f"Preview selected piece: {piece.n_cells} faces.")
        except Exception as exc:  # noqa: BLE001 - UI boundary
            logger.exception("Selected preview failed")
            self.status_label.setText(f"Error preview selección: {exc}")

    def export_selected_piece(self) -> None:
        try:
            piece = self._selected_piece_surface()
            path, _ = QFileDialog.getSaveFileName(self, "Exportar selección STL", "split3r_selected_piece.stl", "STL (*.stl)")
            if not path:
                return
            piece.save(path)
            self.status_label.setText(f"Selección exportada:\n{path}")
        except Exception as exc:  # noqa: BLE001 - UI boundary
            logger.exception("Selected export failed")
            self.status_label.setText(f"Error exportando selección: {exc}")

    def extract_selection(self) -> None:
        if self.current_mesh is None:
            self.status_label.setText("Primero importá un modelo.")
            return
        if not self.paint_state.include_faces:
            self.status_label.setText("Pintá o expandí una selección roja antes de extraer.")
            return
        try:
            depth = max(0.1, self.depth_slider.value() / 10.0)
            self.status_label.setText("Extrayendo plug/socket...")
            QApplication.processEvents()
            plug, body = extract_plug_socket(self.current_mesh.copy(), set(self.paint_state.include_faces), depth)
            self.last_plug = plug
            self.last_body = body
            if self.plug_actor is not None:
                self.plotter.remove_actor(self.plug_actor)
            if self.body_actor is not None:
                self.plotter.remove_actor(self.body_actor)
            self.body_actor = self.plotter.add_mesh(body, color="#bcb896", opacity=0.28, show_edges=False)
            self.plug_actor = self.plotter.add_mesh(plug, color="#d98613", opacity=1.0, show_edges=False)
            if self.main_actor is not None:
                self.main_actor.SetVisibility(False)
            self.export_btn.setEnabled(True)
            self.plotter.render()
            self.status_label.setText(f"Extracción lista. Plug faces: {plug.n_cells} | Body faces: {body.n_cells}")
        except Exception as exc:  # noqa: BLE001 - UI boundary
            logger.exception("Extraction failed")
            self.status_label.setText(f"Error extrayendo: {exc}")

    def export_last_outputs(self) -> None:
        if self.last_plug is None or self.last_body is None:
            self.status_label.setText("No hay extracción para exportar.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Elegir carpeta de exportación", "")
        if not out_dir:
            return
        try:
            out = Path(out_dir)
            plug_path = out / "split3r_plug.stl"
            body_path = out / "split3r_body_socket.stl"
            self.last_plug.save(plug_path)
            self.last_body.save(body_path)
            self.status_label.setText(f"Exportado:\n{plug_path}\n{body_path}")
        except Exception as exc:  # noqa: BLE001 - UI boundary
            logger.exception("Export failed")
            self.status_label.setText(f"Error exportando: {exc}")

    def _update_labels(self) -> None:
        self.count_label.setText(
            f"Include: {len(self.paint_state.include_faces)} | Exclude: {len(self.paint_state.exclude_faces)}"
        )


def main() -> int:
    app = QApplication(sys.argv)
    window = Split3rStandalone()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
