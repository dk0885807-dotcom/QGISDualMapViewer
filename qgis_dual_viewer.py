import os

from qgis.PyQt.QtWidgets import (
    QAction, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QToolBar
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.gui import (
    QgsMapCanvas,
    QgsLayerTreeView,
    QgsLayerTreeMapCanvasBridge,
    QgsVertexMarker
)
from qgis.core import (
    QgsLayerTree,
    QgsLayerTreeModel,
    QgsPointXY
)


class QGISDualViewer:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        self.main_canvas = iface.mapCanvas()

        self.right_canvas = None
        self.right_root = QgsLayerTree()
        self.bridge = None

        self.map_dock = None
        self.toc_dock = None

        self.cursor_marker = None
        self.toolbar = None

    # ---------------- GUI ----------------
    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        self.action = QAction(
            QIcon(icon_path),
            "QGIS Dual Viewer",
            self.iface.mainWindow()
        )
        self.action.setToolTip("QGIS Dual Viewer")
        self.action.setStatusTip("Open QGIS Dual Viewer")
        self.action.triggered.connect(self.run)

        self.toolbar = self.iface.addToolBar("QGIS Dual Viewer")
        self.toolbar.setObjectName("QGISDualViewerToolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar.addAction(self.action)

        self.iface.addPluginToMenu("View", self.action)

    def unload(self):
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
        self.iface.removePluginMenu("View", self.action)

    # ---------------- Dock cleanup ----------------
    def _on_map_dock_closed(self):
        self.map_dock = None
        self.right_canvas = None
        self.bridge = None
        self.cursor_marker = None

    def _on_toc_dock_closed(self):
        self.toc_dock = None

    # ---------------- Main ----------------
    def run(self):

        # ===== Right Map Viewer =====
        if self.map_dock is None:
            self.map_dock = QDockWidget("Right Map – Viewer", self.iface.mainWindow())
            self.map_dock.setFeatures(
                QDockWidget.DockWidgetMovable |
                QDockWidget.DockWidgetFloatable |
                QDockWidget.DockWidgetClosable
            )
            self.map_dock.setAttribute(Qt.WA_DeleteOnClose)
            self.map_dock.destroyed.connect(self._on_map_dock_closed)

            container = QWidget()
            layout = QVBoxLayout(container)

            self.right_canvas = QgsMapCanvas()
            self.right_canvas.setCanvasColor(Qt.white)
            self.right_canvas.setExtent(self.main_canvas.extent())
            layout.addWidget(self.right_canvas)

            self.map_dock.setWidget(container)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.map_dock)
        else:
            self.map_dock.show()
            self.map_dock.raise_()

        # ===== Right Map Layers (TOC) =====
        if self.toc_dock is None:
            self.toc_dock = QDockWidget("Right Map – Layers", self.iface.mainWindow())
            self.toc_dock.setFeatures(
                QDockWidget.DockWidgetMovable |
                QDockWidget.DockWidgetFloatable |
                QDockWidget.DockWidgetClosable
            )
            self.toc_dock.setAttribute(Qt.WA_DeleteOnClose)
            self.toc_dock.destroyed.connect(self._on_toc_dock_closed)

            toc_container = QWidget()
            toc_layout = QVBoxLayout(toc_container)

            btn_add = QPushButton("Add → Right Map")
            btn_add.clicked.connect(self.add_selected_layers)

            toc_layout.addWidget(btn_add)
            toc_layout.addWidget(QLabel("Independent Layer Panel"))

            # ---- Layer tree with visibility support ----
            self.tree_view = QgsLayerTreeView()
            self.tree_model = QgsLayerTreeModel(self.right_root)
            self.tree_model.setFlag(QgsLayerTreeModel.AllowNodeReorder)
            self.tree_model.setFlag(QgsLayerTreeModel.AllowNodeRename)
            self.tree_model.setFlag(QgsLayerTreeModel.AllowNodeChangeVisibility)

            self.tree_view.setModel(self.tree_model)
            toc_layout.addWidget(self.tree_view)

            self.toc_dock.setWidget(toc_container)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.toc_dock)
        else:
            self.toc_dock.show()
            self.toc_dock.raise_()

        # ===== Bridge (keeps layer on/off in sync) =====
        if self.right_canvas and not self.bridge:
            self.bridge = QgsLayerTreeMapCanvasBridge(
                self.right_root, self.right_canvas
            )

        # ===== Cursor marker (overlay only) =====
        if self.right_canvas and not self.cursor_marker:
            self.cursor_marker = QgsVertexMarker(self.right_canvas)
            self.cursor_marker.setIconType(QgsVertexMarker.ICON_CROSS)
            self.cursor_marker.setColor(Qt.red)
            self.cursor_marker.setIconSize(12)
            self.cursor_marker.setPenWidth(2)
            self.cursor_marker.hide()

        # Sync extent & cursor always ON
        self.main_canvas.extentsChanged.connect(self.sync_extent_func)
        self.main_canvas.xyCoordinates.connect(self.sync_cursor_func)

        self.refresh_right_canvas()

        print("QGIS Dual Viewer opened")

    # ---------------- Logic ----------------
    def add_selected_layers(self):
        if not self.right_canvas:
            return

        for lyr in self.iface.layerTreeView().selectedLayers():
            if not self.right_root.findLayer(lyr.id()):
                self.right_root.addLayer(lyr)

        self.refresh_right_canvas()

    def refresh_right_canvas(self):
        if not self.right_canvas:
            return

        layers = [
            n.layer() for n in self.right_root.findLayers()
            if n.isVisible() and n.layer()
        ]
        self.right_canvas.setLayers(layers)
        self.right_canvas.refresh()

    def sync_extent_func(self):
        if self.right_canvas:
            self.right_canvas.setExtent(self.main_canvas.extent())
            self.right_canvas.refresh()

    def sync_cursor_func(self, pt: QgsPointXY):
        if self.cursor_marker:
            self.cursor_marker.setCenter(pt)
            self.cursor_marker.show()
