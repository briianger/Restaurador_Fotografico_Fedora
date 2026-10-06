"""Procesamiento clásico local. Todos los parámetros son independientes de IRS."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass
class Settings:
    balance: float = 0.8
    noise: float = 0.35
    contrast: float = 0.25
    shadows: float = 0.25
    brightness: float = 0.0
    saturation: float = 1.0
    sharpness: float = 0.35
    scale: int = 1
    crop: float = 0.0


PRESETS = {
    "Acabado actual": Settings(),
    "Restauración suave": Settings(balance=0.5, noise=0.2, contrast=0.15,
                                   shadows=0.15, sharpness=0.2),
    "Foto deteriorada": Settings(balance=0.9, noise=0.55, contrast=0.4,
                                 shadows=0.4, sharpness=0.35),
    "Sin ajustes": Settings(balance=0, noise=0, contrast=0, shadows=0,
                           sharpness=0),
}


def byte(value):
    return np.clip(np.rint(value), 0, 255).astype(np.uint8)


def load_image(path):
    with Image.open(path) as source:
        if source.width * source.height > 24_000_000:
            raise ValueError("La imagen supera 24 megapíxeles. Reduce su tamaño antes de abrirla.")
        info = {"icc_profile": source.info.get("icc_profile"),
                "source": str(Path(path).resolve())}
        # Normalizar perfiles CMYK/RGB a sRGB antes de procesar, si son válidos.
        corrected = ImageOps.exif_transpose(source)
        if info["icc_profile"]:
            try:
                from PIL import ImageCms
                import io
                srgb = ImageCms.createProfile("sRGB")
                corrected = ImageCms.profileToProfile(
                    corrected, ImageCms.ImageCmsProfile(io.BytesIO(info["icc_profile"])),
                    srgb, outputMode="RGB")
                info["icc_profile"] = ImageCms.ImageCmsProfile(srgb).tobytes()
            except (ValueError, OSError, TypeError, ImageCms.PyCMSError):
                info["icc_profile"] = None
        return np.array(corrected.convert("RGB")), info


def process(rgb, settings, white=None, repair=None, notify=lambda text: None):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Se requiere una imagen RGB de 8 bits.")
    s = settings
    h, w = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    notify("Reparando marcas…")
    if repair is not None and np.any(repair):
        if repair.shape != (h, w):
            raise ValueError("La máscara de reparación no coincide con la imagen.")
        bgr = cv2.inpaint(bgr, repair.astype(np.uint8), 3, cv2.INPAINT_TELEA)
    if s.noise > 0:
        notify("Reduciendo ruido y conservando bordes…")
        # Non-local means con ventanas pequeñas para un coste moderado en CPU.
        clean = cv2.fastNlMeansDenoisingColored(
            bgr, None, 1 + 5 * s.noise, 2 + 8 * s.noise, 7, 21)
        bgr = cv2.addWeighted(bgr, 0.4, clean, 0.6, 0)
    f = bgr.astype(np.float32)
    notify("Equilibrando color e iluminación…")
    if s.balance > 0:
        if white is not None:
            x, y = white
            patch = f[max(0, y-5):min(h, y+6), max(0, x-5):min(w, x+6)]
            reference = np.median(patch.reshape(-1, 3), axis=0)
        else:
            # Solo píxeles claros con baja saturación; descartar blancos puros.
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            candidates = (hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 140) & (hsv[:, :, 2] < 248)
            reference = (np.median(f[candidates], axis=0) if np.count_nonzero(candidates) > 50
                         else np.percentile(f.reshape(-1, 3), 95, axis=0))
        gains = np.clip(np.mean(reference) / np.maximum(reference, 1), 0.7, 1.4) ** s.balance
        f *= gains
    bgr = byte(f)
    if s.contrast > 0:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        adjusted = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        lab[:, :, 0] = cv2.addWeighted(lab[:, :, 0], 1-s.contrast, adjusted, s.contrast, 0)
        bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    f = bgr.astype(np.float32) / 255
    if s.shadows > 0:
        luma = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        ambient = cv2.GaussianBlur(luma, (0, 0), max(2, min(h, w)/40))
        weight = (0.55 * s.shadows * (1-ambient)**2)[:, :, None]
        f = f * (1-weight) + (1-(1-f)**2) * weight
    if s.brightness:
        f = np.clip(f, 0, 1) ** (2 ** (-s.brightness))
    bgr = byte(f * 255)
    if s.saturation != 1:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hsv[:, :, 1] = byte(hsv[:, :, 1].astype(np.float32) * s.saturation)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    if s.sharpness > 0:
        notify("Ajustando nitidez…")
        ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        y = ycc[:, :, 0].astype(np.float32)
        detail = y - cv2.GaussianBlur(y, (0, 0), 0.85)
        detail[np.abs(detail) < 3] = 0
        ycc[:, :, 0] = byte(y + s.sharpness * np.clip(detail, -18, 18))
        bgr = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
    result = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    bottom = max(1, round(h * (1 - s.crop)))
    result = result[:bottom].copy()
    if s.scale not in (1, 2, 3):
        raise ValueError("La ampliación debe ser 1×, 2× o 3×.")
    if result.shape[0] * result.shape[1] * s.scale**2 > 36_000_000:
        raise ValueError("La exportación supera 36 megapíxeles. Elige una ampliación menor.")
    if s.scale != 1:
        notify("Ampliando con interpolación de alta calidad…")
        result = np.array(Image.fromarray(result).resize(
            (w*s.scale, bottom*s.scale), Image.Resampling.LANCZOS))
    return result


def save_image(rgb, path, info=None):
    """Escritura atómica y verificación; la GUI pide confirmar cualquier reemplazo."""
    path = Path(path)
    if info and path.resolve() == Path(info["source"]).resolve():
        raise ValueError("Guarda con otro nombre para conservar la imagen original.")
    fmt = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}.get(path.suffix.lower())
    if fmt is None:
        raise ValueError("Usa una extensión .png, .jpg o .jpeg.")
    options = {"icc_profile": info["icc_profile"]} if info and info.get("icc_profile") else {}
    if fmt == "JPEG":
        options.update(quality=95, subsampling=0)
    fd, temp = tempfile.mkstemp(prefix=".restaurador-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    try:
        Image.fromarray(rgb).save(temp, format=fmt, **options)
        with Image.open(temp) as checked:
            checked.verify()
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_recipe(path, settings, white, source):
    Path(path).write_text(json.dumps({"version": 1, "source": str(source),
        "settings": asdict(settings), "white_point": white}, indent=2,
        ensure_ascii=False), encoding="utf-8")
