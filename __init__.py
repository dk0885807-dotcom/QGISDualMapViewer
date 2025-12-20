def classFactory(iface):
    from .qgis_dual_viewer import QGISDualViewer
    return QGISDualViewer(iface)
