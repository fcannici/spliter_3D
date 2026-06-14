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

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.main_window is not None:
            vtk_pos = (ev.pos().x(), self.height() - ev.pos().y())
            modifiers = ev.modifiers()
            if modifiers & Qt.KeyboardModifier.AltModifier:
                self.main_window.paint_at(vtk_pos, mode="exclude")
                return
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.main_window.paint_at(vtk_pos, mode="include")
                return
            self.main_window.paint_at(vtk_pos, mode=self.main_window.current_paint_mode())
            return
        super().mousePressEvent(ev)


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
        paint_layout.addWidget(QLabel("Click pinta. Ctrl+Click Include. Alt+Click Exclude."))
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
        self.extract_btn = QPushButton("Extract Plug + Socket (próximo paso)")
        self.extract_btn.setEnabled(False)
        extract_layout.addWidget(self.extract_btn)
        extract_layout.addWidget(QLabel("MVP actual: selección standalone. Backend Blender headless sigue luego."))
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
            validate_polydata(self.current_mesh)
            self.adjacency = build_adjacency_dict(
                self.trimesh_mesh.face_adjacency,
                self.trimesh_mesh.face_adjacency_angles,
            )
            self.paint_state.clear()
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
        return int(self.cell_picker.GetCellId())

    def _brush_faces(self, seed_face: int) -> set[int]:
        # First MVP: single-face paint. Keeping this explicit makes the later visible brush
        # radius implementation straightforward without changing the selection model.
        return {seed_face} if seed_face >= 0 else set()

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
