import os

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget,
    QVBoxLayout, QPushButton, QMenu,
    QToolButton, QHBoxLayout
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

        # Left (main) canvas
        self.left_canvas = iface.mapCanvas()

        # Right canvas
        self.right_canvas = None

        # Right layer tree
        self.right_root = QgsLayerTree()
        self.bridge = None

        # UI
        self.map_dock = None
        self.toc_dock = None
        self.toolbar = None

        self.btn_toggle_dock = None

        # Cursor markers
        self.cursor_marker_outer = None
        self.cursor_marker_inner = None

        self._syncing = False

    # --------------------------------------------------
    # GUI
    # --------------------------------------------------

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        self.toolbar = self.iface.addToolBar("QGIS Dual Viewer")
        self.toolbar.setObjectName("QGISDualViewerToolbar")

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(3)

        container.setStyleSheet("""
            QWidget {
                border: 1px solid #b0b0b0;
                background: transparent;
            }
        """)

        btn_open = QToolButton()
        btn_open.setIcon(QIcon(icon_path))
        btn_open.setText("QGIS Dual Viewer")
        btn_open.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_open.clicked.connect(self.run)
        btn_open.setCursor(Qt.PointingHandCursor)

        self.btn_toggle_dock = QToolButton()
        self.btn_toggle_dock.setText("Undock")
        self.btn_toggle_dock.clicked.connect(self.toggle_dock)
        self.btn_toggle_dock.setCursor(Qt.PointingHandCursor)

        btn_close = QToolButton()
        btn_close.setText("Close Viewer")
        btn_close.clicked.connect(self.close_viewer)
        btn_close.setCursor(Qt.PointingHandCursor)

        layout.addWidget(btn_open)
        layout.addWidget(self.btn_toggle_dock)
        layout.addWidget(btn_close)

        self.toolbar.addWidget(container)

    def unload(self):
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)

    # --------------------------------------------------
    # MAIN
    # --------------------------------------------------

    def run(self):

        # ---------- RIGHT MAP VIEW ----------
        if self.map_dock is None:
            self.map_dock = QDockWidget("Right Viewer", self.iface.mainWindow())

            self.map_dock.setFeatures(
                QDockWidget.DockWidgetMovable |
                QDockWidget.DockWidgetFloatable
            )

            # Clean docked look
            self.map_dock.setTitleBarWidget(QWidget())

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)

            self.right_canvas = QgsMapCanvas(container)
            self.right_canvas.setCanvasColor(Qt.white)
            self.right_canvas.setDestinationCrs(
                self.left_canvas.mapSettings().destinationCrs()
            )

            layout.addWidget(self.right_canvas)
            self.map_dock.setWidget(container)

            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.map_dock)
        else:
            self.map_dock.show()
            self.map_dock.raise_()

        # ---------- RIGHT LAYERS PANEL ----------
        if self.toc_dock is None:
            self.toc_dock = QDockWidget("Right Map – Layers", self.iface.mainWindow())

            toc_container = QWidget()
            toc_layout = QVBoxLayout(toc_container)
            toc_layout.setContentsMargins(4, 4, 4, 4)

            btn_add = QPushButton("Add → Right Map")
            btn_add.clicked.connect(self.add_selected_layers)
            toc_layout.addWidget(btn_add)

            self.tree_view = QgsLayerTreeView()
            self.tree_model = QgsLayerTreeModel(self.right_root)
            self.tree_model.setFlag(QgsLayerTreeModel.AllowNodeChangeVisibility, True)
            self.tree_model.setFlag(QgsLayerTreeModel.AllowNodeReorder, True)

            self.tree_view.setModel(self.tree_model)
            self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.tree_view.customContextMenuRequested.connect(
                self.right_layer_context_menu
            )

            toc_layout.addWidget(self.tree_view)
            self.toc_dock.setWidget(toc_container)

            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.toc_dock)

            for dock in self.iface.mainWindow().findChildren(QDockWidget):
                if dock.windowTitle() == "Layers":
                    self.iface.mainWindow().splitDockWidget(
                        dock, self.toc_dock, Qt.Vertical
                    )
                    break

        # ---------- BRIDGE ----------
        if not self.bridge:
            self.bridge = QgsLayerTreeMapCanvasBridge(
                self.right_root, self.right_canvas
            )
            self.bridge.setAutoSetupOnFirstLayer(False)

        # ---------- CURSOR ----------
        if not self.cursor_marker_outer:
            self.cursor_marker_outer = QgsVertexMarker(self.right_canvas)
            self.cursor_marker_outer.setIconType(QgsVertexMarker.ICON_CROSS)
            self.cursor_marker_outer.setColor(Qt.black)
            self.cursor_marker_outer.setIconSize(16)
            self.cursor_marker_outer.setPenWidth(3)

        if not self.cursor_marker_inner:
            self.cursor_marker_inner = QgsVertexMarker(self.right_canvas)
            self.cursor_marker_inner.setIconType(QgsVertexMarker.ICON_CROSS)
            self.cursor_marker_inner.setColor(Qt.white)
            self.cursor_marker_inner.setIconSize(10)
            self.cursor_marker_inner.setPenWidth(2)

        # ---------- SYNC ----------
        self.left_canvas.extentsChanged.connect(self.sync_left_to_right)
        self.left_canvas.xyCoordinates.connect(self.sync_cursor)
        self.right_canvas.xyCoordinates.connect(self.sync_cursor)
        self.left_canvas.destinationCrsChanged.connect(
            self.sync_left_crs_to_right
        )

    # --------------------------------------------------
    # TOOLBAR ACTIONS
    # --------------------------------------------------

    def toggle_dock(self):
        if not self.map_dock:
            return

        if self.map_dock.isFloating():
            # Dock back (no title bar)
            self.map_dock.setFloating(False)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.map_dock)
            self.map_dock.setTitleBarWidget(QWidget())
            self.btn_toggle_dock.setText("Undock")

        else:
            # True floating window
            self.map_dock.setTitleBarWidget(None)
            self.map_dock.setWindowTitle("Right Viewer")
            self.map_dock.setFloating(True)
            self.map_dock.show()
            self.map_dock.raise_()
            self.btn_toggle_dock.setText("Dock")

    def close_viewer(self):
        if self.map_dock:
            self.iface.removeDockWidget(self.map_dock)
            self.map_dock.deleteLater()
            self.map_dock = None

        if self.toc_dock:
            self.iface.removeDockWidget(self.toc_dock)
            self.toc_dock.deleteLater()
            self.toc_dock = None

        self.right_canvas = None
        self.bridge = None
        self.cursor_marker_outer = None
        self.cursor_marker_inner = None

        self.btn_toggle_dock.setText("Undock")

    # --------------------------------------------------
    # LAYERS
    # --------------------------------------------------

    def add_selected_layers(self):
        for lyr in self.iface.layerTreeView().selectedLayers():
            if not self.right_root.findLayer(lyr.id()):
                self.right_root.addLayer(lyr)

        if len(self.right_root.findLayers()) == 1:
            self.right_canvas.zoomToFullExtent()

    def right_layer_context_menu(self, pos):
        menu = QMenu()
        remove_action = menu.addAction("Remove selected layer(s)")
        clear_action = menu.addAction("Clear right view")

        action = menu.exec_(self.tree_view.mapToGlobal(pos))

        if action == remove_action:
            for node in self.tree_view.selectedNodes():
                self.right_root.removeChildNode(node)
        elif action == clear_action:
            self.right_root.clear()

    # --------------------------------------------------
    # SYNC
    # --------------------------------------------------

    def sync_left_to_right(self):
        if self._syncing or not self.right_canvas:
            return
        self._syncing = True
        self.right_canvas.setExtent(self.left_canvas.extent())
        self.right_canvas.refresh()
        self._syncing = False

    def sync_left_crs_to_right(self):
        if self.right_canvas:
            self.right_canvas.setDestinationCrs(
                self.left_canvas.mapSettings().destinationCrs()
            )
            self.right_canvas.refresh()

    def sync_cursor(self, pt: QgsPointXY):
        if self.cursor_marker_outer and self.cursor_marker_inner:
            self.cursor_marker_outer.setCenter(pt)
            self.cursor_marker_inner.setCenter(pt)
            self.right_canvas.refresh()
