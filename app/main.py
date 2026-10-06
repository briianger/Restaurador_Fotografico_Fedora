"""Interfaz Qt en español para restauración fotográfica local."""
from dataclasses import replace
from pathlib import Path
import sys
import numpy as np
import cv2
from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QSlider, QComboBox, QFileDialog,
    QMessageBox, QScrollArea, QSplitter, QProgressBar, QSpinBox, QButtonGroup)
from engine import Settings, PRESETS, load_image, process, save_image, save_recipe


STYLE = """
QMainWindow,QWidget {background:#101820;color:#e8eef4;font-family:Sans Serif;font-size:13px;}
QLabel#title {font-size:25px;font-weight:bold;}
QLabel#muted {color:#9eb1c3;}
QPushButton {background:#223243;border:1px solid #344b61;border-radius:7px;padding:9px 14px;}
QPushButton:hover {background:#30465d;}
QPushButton:checked {background:#305c67;border-color:#6bdbc6;}
QPushButton#primary {background:#66d9c0;color:#102b2b;font-weight:bold;}
QPushButton:disabled {background:#1b2531;color:#657587;border-color:#253343;}
QPushButton#primary:disabled {background:#1b2531;color:#657587;border-color:#253343;}
QComboBox,QSpinBox {background:#223243;border:1px solid #344b61;padding:6px;border-radius:5px;}
QSlider::groove:horizontal {height:5px;background:#2c4155;border-radius:2px;}
QSlider::sub-page:horizontal {background:#66d9c0;}
QSlider::handle:horizontal {background:#e8eef4;width:13px;margin:-5px 0;border-radius:6px;}
QScrollArea {border:0;}
QProgressBar {border:0;background:#223243;height:5px;}
QProgressBar::chunk {background:#66d9c0;}
QSplitter::handle {background:#283949;}
"""


class Preview(QWidget):
    clicked = Signal(int, int)
    stroke = Signal(int, int, int, int)

    def __init__(self, title):
        super().__init__()
        self.title = title
        self.rgb = None
        self.overlay = None
        self.image = None
        self.rect = QRectF()
        self.last = None
        self.mode = "view"
        self.setMinimumSize(220, 280)

    def set_image(self, rgb, overlay=None):
        self.rgb = rgb
        self.overlay = overlay
        if rgb is not None:
            a = np.ascontiguousarray(rgb)
            if overlay is not None and np.any(overlay):
                a = a.copy()
                mask = overlay > 0
                a[mask] = (a[mask] * 0.45 + np.array([245, 105, 70]) * 0.55).astype(np.uint8)
            self.image = QImage(a.data, a.shape[1], a.shape[0], a.strides[0],
                                QImage.Format.Format_RGB888).copy()
        else:
            self.image = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.contentsRect(), QColor("#17232f"))
        p.setPen(QColor("#bdcede"))
        p.drawText(14, 24, self.title)
        if self.image is None:
            p.setPen(QColor("#8097ad"))
            p.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignCenter, "Abre una fotografía para empezar")
            self.rect = QRectF()
            return
        iw, ih = self.image.width(), self.image.height()
        ratio = min(max(1, self.width()-24)/iw, max(1, self.height()-60)/ih)
        dw, dh = iw*ratio, ih*ratio
        self.rect = QRectF((self.width()-dw)/2, 40+(self.height()-60-dh)/2, dw, dh)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(self.rect, self.image)
        p.setPen(QColor("#8da5bc"))
        p.drawText(14, self.height()-9, f"{iw} × {ih} píxeles")

    def position(self, event):
        if self.rgb is None or not self.rect.contains(event.position()):
            return None
        x = int((event.position().x()-self.rect.x()) / self.rect.width() * self.rgb.shape[1])
        y = int((event.position().y()-self.rect.y()) / self.rect.height() * self.rgb.shape[0])
        return min(x, self.rgb.shape[1]-1), min(y, self.rgb.shape[0]-1)

    def mousePressEvent(self, event):
        pos = self.position(event)
        if pos and event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "white":
                self.clicked.emit(*pos)
            elif self.mode == "repair":
                self.last = pos
                self.stroke.emit(*pos, *pos)

    def mouseMoveEvent(self, event):
        pos = self.position(event)
        if self.mode == "repair" and self.last and pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.stroke.emit(*self.last, *pos)
            self.last = pos

    def mouseReleaseEvent(self, event):
        self.last = None


class Worker(QThread):
    status = Signal(str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, rgb, settings, white, repair):
        super().__init__()
        self.rgb = rgb
        self.settings = settings
        self.white = white
        self.repair = repair

    def run(self):
        try:
            self.result.emit(process(self.rgb, self.settings, self.white, self.repair,
                                     self.status.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Restaurador Fotográfico · Local")
        self.resize(1320, 850)
        self.original = self.result = self.mask = None
        self.white = None
        self.path = None
        self.info = {}
        self.worker = None
        self.applied = None
        self.last_white = None
        self.dirty = False
        self.sliders = {}
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 16)
        heading = QHBoxLayout()
        title = QLabel("Restaurador Fotográfico")
        title.setObjectName("title")
        heading.addWidget(title)
        heading.addStretch()
        self.open_button = QPushButton("Abrir imagen")
        self.open_button.clicked.connect(self.open_dialog)
        heading.addWidget(self.open_button)
        self.save_button = QPushButton("Guardar resultado")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_dialog)
        heading.addWidget(self.save_button)
        layout.addLayout(heading)
        subtitle = QLabel("Color, iluminación y detalle · Procesamiento local sin conexión")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        splitter = QSplitter()
        self.left = Preview("ORIGINAL · selecciona aquí el blanco o las marcas")
        self.right = Preview("RESULTADO")
        previews = QSplitter()
        previews.addWidget(self.left)
        previews.addWidget(self.right)
        previews.setSizes([450, 450])
        self.left.clicked.connect(self.set_white)
        self.left.stroke.connect(self.paint_mask)
        splitter.addWidget(previews)
        panel = QWidget()
        self.panel = panel
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(370)
        form = QVBoxLayout(panel)
        form.addWidget(QLabel("Perfil de mejora"))
        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.currentTextChanged.connect(self.select_preset)
        form.addWidget(self.preset)
        specs = [("balance", "Corrección de color", 0, 100),
                 ("noise", "Reducir ruido", 0, 100),
                 ("contrast", "Contraste por zonas", 0, 100),
                 ("shadows", "Aclarar sombras", 0, 100),
                 ("brightness", "Brillo", -50, 50),
                 ("saturation", "Intensidad de color", 0, 150),
                 ("sharpness", "Nitidez", 0, 100),
                 ("crop", "Recorte inferior (%)", 0, 20)]
        for key, text, minimum, maximum in specs:
            line = QHBoxLayout()
            line.addWidget(QLabel(text))
            value = QLabel()
            line.addStretch()
            line.addWidget(value)
            form.addLayout(line)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.valueChanged.connect(lambda n, label=value: label.setText(str(n)))
            slider.valueChanged.connect(self.mark_dirty)
            self.sliders[key] = slider
            form.addWidget(slider)
        self.scale = QComboBox()
        self.scale.addItems(["1× · resolución original", "2× · interpolación", "3× · interpolación"])
        self.scale.currentIndexChanged.connect(self.mark_dirty)
        form.addWidget(QLabel("Tamaño de exportación"))
        form.addWidget(self.scale)
        form.addWidget(QLabel("Herramientas sobre el original"))
        tools = QHBoxLayout()
        self.tool_group = QButtonGroup(self)
        for text, mode in [("Ver", "view"), ("Blanco", "white"), ("Reparar", "repair")]:
            button = QPushButton(text)
            button.setCheckable(True)
            self.tool_group.addButton(button)
            if mode == "view": button.setChecked(True)
            button.clicked.connect(lambda checked=False, m=mode: self.set_mode(m))
            tools.addWidget(button)
        form.addLayout(tools)
        brushline = QHBoxLayout()
        brushline.addWidget(QLabel("Pincel (píxeles)"))
        self.brush = QSpinBox()
        self.brush.setRange(1, 60)
        self.brush.setValue(8)
        brushline.addWidget(self.brush)
        form.addLayout(brushline)
        clear = QPushButton("Limpiar blanco y marcas")
        clear.clicked.connect(self.clear_tools)
        form.addWidget(clear)
        help_text = QLabel("Blanco: pulsa sobre una zona blanca o gris.\nReparar: pinta pequeñas motas o arañazos.\nDespués pulsa Aplicar mejora.")
        help_text.setWordWrap(True)
        help_text.setObjectName("muted")
        form.addWidget(help_text)
        self.apply_button = QPushButton("Aplicar mejora")
        self.apply_button.setObjectName("primary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        form.insertWidget(2, self.apply_button)
        recipe = QPushButton("Guardar ajustes (.json)")
        recipe.clicked.connect(self.save_recipe_dialog)
        form.addWidget(recipe)
        note = QLabel("La ampliación conserva píxeles existentes; no reconstruye detalles con IA.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addWidget(note)
        form.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(300)
        scroll.setMaximumWidth(390)
        splitter.addWidget(scroll)
        splitter.setSizes([920, 320])
        layout.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("Abre una fotografía · PNG, JPEG, TIFF, BMP o WebP")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.select_preset(self.preset.currentText())
        open_action = QAction("Abrir", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_dialog)
        self.addAction(open_action)
        save_action = QAction("Guardar", self)
        save_action.setShortcut("Ctrl+Shift+S")
        save_action.triggered.connect(self.save_dialog)
        self.addAction(save_action)

    def settings(self):
        values = {k: v.value()/100 for k, v in self.sliders.items()}
        return Settings(**values, scale=self.scale.currentIndex()+1)

    def select_preset(self, name):
        s = PRESETS[name]
        for key, slider in self.sliders.items():
            slider.setValue(round(getattr(s, key)*100))
        self.scale.setCurrentIndex(s.scale-1)

    def mark_dirty(self, *args):
        if self.result is not None:
            self.dirty = True
            self.save_button.setEnabled(False)
            self.status.setText("Ajustes cambiados · pulsa Aplicar mejora para actualizar el resultado")

    def set_mode(self, mode):
        self.left.mode = mode
        self.left.setCursor(Qt.CursorShape.ArrowCursor if mode == "view"
                            else Qt.CursorShape.CrossCursor)

    def set_white(self, x, y):
        if self.busy(): return
        self.white = (x, y)
        self.mark_dirty()
        self.status.setText(f"Blanco seleccionado en ({x}, {y}) · pulsa Aplicar mejora")

    def paint_mask(self, x1, y1, x2, y2):
        if self.mask is None or (self.worker and self.worker.isRunning()):
            return
        cv2.line(self.mask, (x1, y1), (x2, y2), 255, self.brush.value())
        cv2.circle(self.mask, (x2, y2), max(1, self.brush.value()//2), 255, -1)
        self.left.set_image(self.original, self.mask)
        self.mark_dirty()

    def clear_tools(self):
        if self.busy(): return
        self.white = None
        if self.mask is not None:
            self.mask.fill(0)
            self.left.set_image(self.original)
        self.mark_dirty()

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def open_dialog(self):
        if self.busy(): return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir fotografía", "",
            "Imágenes (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;Todos los archivos (*)")
        if path: self.open_path(path)

    def open_path(self, path):
        try:
            rgb, info = load_image(path)
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo abrir", str(exc))
            return False
        self.original, self.info = rgb, info
        self.path = Path(path)
        self.result = None
        self.white = None
        self.mask = np.zeros(rgb.shape[:2], np.uint8)
        self.left.set_image(rgb)
        self.right.set_image(None)
        self.save_button.setEnabled(False)
        self.apply_button.setEnabled(True)
        self.status.setText(f"{self.path.name} · {rgb.shape[1]} × {rgb.shape[0]} · ajusta y aplica")
        return True

    def apply(self):
        if self.original is None or self.busy(): return
        self.applied = replace(self.settings())
        self.last_white = self.white
        self.worker = Worker(self.original.copy(), self.applied, self.white, self.mask.copy())
        self.worker.status.connect(self.status.setText)
        self.worker.result.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.open_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.preset.setEnabled(False)
        self.scale.setEnabled(False)
        self.left.mode = "view"
        self.panel.setEnabled(False)
        for slider in self.sliders.values(): slider.setEnabled(False)
        self.progress.setRange(0, 0)
        self.worker.start()

    def completed(self, rgb):
        self.result = rgb
        self.dirty = False
        self.right.set_image(rgb)
        self.save_button.setEnabled(True)
        self.status.setText(f"Resultado listo · {rgb.shape[1]} × {rgb.shape[0]} · guarda con un nombre nuevo")

    def failed(self, message):
        self.status.setText("No se pudo aplicar la mejora")
        QMessageBox.critical(self, "Error de procesamiento", message)

    def finished(self):
        self.panel.setEnabled(True)
        self.open_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.preset.setEnabled(True)
        self.scale.setEnabled(True)
        for slider in self.sliders.values(): slider.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if self.result is not None else 0)
        button = self.tool_group.checkedButton()
        if button:
            self.set_mode({"Ver":"view", "Blanco":"white", "Reparar":"repair"}[button.text()])

    def save_dialog(self):
        if self.result is None or self.busy() or self.dirty: return
        default = str(self.path.with_name(self.path.stem+"_restaurada.png"))
        path, selected = QFileDialog.getSaveFileName(self, "Guardar resultado", default,
                                                    "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path: return
        if not Path(path).suffix:
            path += ".jpg" if selected.startswith("JPEG") else ".png"
        try:
            save_image(self.result, path, self.info)
            self.status.setText(f"Guardado y verificado: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))

    def save_recipe_dialog(self):
        if self.path is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar ajustes", str(
            self.path.with_name(self.path.stem+"_ajustes.json")), "JSON (*.json)")
        if path:
            try:
                save_recipe(path, self.settings(), self.white, self.path)
                self.status.setText(f"Ajustes guardados: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "No se pudo guardar", str(exc))

    def closeEvent(self, event):
        if self.busy():
            QMessageBox.information(self, "Procesamiento en curso",
                "Espera a que termine el procesamiento antes de cerrar.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Restaurador Fotográfico")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        window.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
