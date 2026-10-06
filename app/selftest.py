"""Verificación del motor, exportación y GUI sin pantalla física."""
from pathlib import Path
import os
import sys
import tempfile
import time
import numpy as np
from PIL import Image
from engine import Settings, load_image, process, save_image


def run():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        # Imagen sintética: textura, degradado y una marca aislada.
        yy, xx = np.mgrid[:96, :128]
        rgb = np.stack([70+xx, 80+xx//2, 90+yy], axis=2).astype(np.uint8)
        rgb[45:48, 60:63] = 255
        source = base / "entrada.png"
        Image.fromarray(rgb).save(source)
        loaded, info = load_image(source)
        assert np.array_equal(loaded, rgb)
        s = Settings(balance=0, noise=0, contrast=0, shadows=0, sharpness=0)
        assert np.array_equal(process(rgb, s), rgb), "Sin ajustes debe conservar los píxeles"
        mask = np.zeros(rgb.shape[:2], np.uint8)
        mask[44:49, 59:64] = 255
        repaired = process(rgb, s, repair=mask)
        assert repaired[46, 61].mean() < rgb[46, 61].mean() - 30
        result = process(rgb, Settings(scale=2, crop=0.1), white=(30, 30), repair=mask)
        assert result.shape == (172, 256, 3)
        assert result.dtype == np.uint8
        assert not np.array_equal(result[::2, ::2], rgb[:86])
        for extension in ("png", "jpg"):
            path = base / f"resultado.{extension}"
            save_image(result, path, info)
            with Image.open(path) as im:
                assert im.size == (256, 172)
                im.verify()
        try:
            save_image(result, source, info)
            raise AssertionError("Debe proteger la imagen original")
        except ValueError:
            pass
        for scale in (0, 4):
            try:
                process(rgb, Settings(scale=scale, noise=0))
                raise AssertionError("Debe rechazar la ampliación inválida")
            except ValueError:
                pass
        oriented = base / "orientada.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.fromarray(rgb).save(oriented, exif=exif)
        rotated, _ = load_image(oriented)
        assert rotated.shape[:2] == (128, 96)
        print("OK: motor, reparación, recorte, ampliación, EXIF y exportación PNG/JPEG")

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from main import Window, STYLE
        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)
        window = Window()
        window.show()
        app.processEvents()
        assert window.open_path(source)
        window.set_white(30, 30)
        window.paint_mask(60, 45, 62, 47)
        assert window.mask.any()
        window.apply()
        deadline = time.monotonic() + 30
        while (window.busy() or window.result is None) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert window.result is not None, "El procesamiento en segundo plano debe terminar"
        assert window.save_button.isEnabled()
        window.sliders["brightness"].setValue(12)
        assert window.dirty and not window.save_button.isEnabled()
        window.clear_tools()
        assert window.white is None and not window.mask.any()
        app.processEvents()
        if "--screenshot" in sys.argv:
            index = sys.argv.index("--screenshot")
            window.grab().save(sys.argv[index+1])
        window.close()
        print("OK: GUI Qt, apertura, pincel, blanco, trabajador y detección de cambios")


if __name__ == "__main__":
    run()
