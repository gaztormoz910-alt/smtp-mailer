# -*- coding: utf-8 -*-
"""Сборка иконки Pinion из ОДНОГО исходника (assets/Pinion-source.webp) в
assets/Pinion.ico с 10 размерами.

Почему так, а не «сохранить .ico одной строкой Pillow»:
- Pillow при сохранении .ico сам ужимает картинку в sRGB. sRGB — нелинейная
  шкала, наивное усреднение соседних пикселей гасит яркие тонкие линии на
  тёмном фоне (у нас — светлый стержень пера на почти чёрной плитке). Поэтому
  каждый кадр считаем вручную: sRGB → линейный свет → премультипликация на
  альфу → LANCZOS → обратно. Иначе мелкие размеры темнеют и мылятся.
- Резкость тоже в линейном свете и с ВОЗВРАТОМ энергии: и unsharp, и обрезка
  тёмной половины ореола в ноль систематически подсвечивают картинку, а нам
  нужно перераспределение контраста, а не рост яркости.
- 10 размеров (не 7): Windows просит 20/40/96 при масштабе экрана 125%/175%;
  если их нет — система сама жмёт чужой размер примитивным алгоритмом.

Запуск: python tools/make_icon.py   (пересобирает мастер и .ico)
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "assets", "Pinion-source.webp")
MASTER = os.path.join(REPO, "assets", "Pinion.png")   # квадратный мастер, полное разрешение
ICO = os.path.join(REPO, "assets", "Pinion.ico")

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
# (радиус, сила) резкости — только для мелких размеров, где ресемплинг съедает границы.
SHARPEN = {16: (0.5, 0.45), 20: (0.5, 0.45), 24: (0.55, 0.40), 32: (0.6, 0.35),
           40: (0.6, 0.30), 48: (0.7, 0.25)}


def _srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def _gaussian_blur_linear(plane, radius):
    """Разделимое гауссово размытие на numpy в float. Своё, потому что
    Pillow.GaussianBlur не умеет режим 'F', а ронять точность линейных значений
    в 8 бит ради размытия — терять именно то, ради чего всё и делается."""
    sigma = max(radius, 1e-3)
    r = max(1, int(round(sigma * 3)))
    xs = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(xs ** 2) / (2 * sigma * sigma))
    k /= k.sum()
    # свёртка по строкам, затем по столбцам (edge-пададдинг, чтобы края не темнели)
    pad = np.pad(plane, ((0, 0), (r, r)), mode="edge")
    tmp = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 1, pad)
    pad = np.pad(tmp, ((r, r), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 0, pad)
    return out


def resize_linear(img, size, sharpen=None):
    arr = np.asarray(img.convert("RGBA"), dtype=np.float64) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]
    lin = _srgb_to_linear(rgb) * alpha[..., None]      # премультипликация на альфу

    planes = []
    for ch in (lin[..., 0], lin[..., 1], lin[..., 2], alpha):
        # режим 'F' — единственный способ отдать Pillow дробные значения без
        # округления до 8 бит: в линейном пространстве тёмные тона занимают
        # такой узкий диапазон, что 8 бит дали бы полосы.
        f = Image.fromarray(ch.astype(np.float32), mode="F")
        planes.append(np.asarray(f.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float64))

    out_a = np.clip(planes[3], 0.0, 1.0)
    safe = np.where(out_a > 1e-6, out_a, 1.0)          # защита от деления на ноль
    out_rgb = np.stack(planes[:3], axis=-1) / safe[..., None]
    out_rgb = np.where(out_a[..., None] > 1e-6, out_rgb, 0.0)

    if sharpen:
        radius, amount = sharpen
        w = out_a[..., None]
        before = float((out_rgb * w).sum())
        blurred = np.stack([_gaussian_blur_linear(out_rgb[..., c], radius) for c in range(3)], axis=-1)
        sharp = out_rgb + amount * (out_rgb - blurred)     # нерезкое маскирование
        after = float((sharp * w).sum())
        if after > 1e-9:
            sharp *= before / after                        # энергия возвращается к исходной
        out_rgb = np.clip(sharp, 0.0, 1.0)

    data = np.concatenate([_linear_to_srgb(out_rgb), out_a[..., None]], axis=-1)
    return Image.fromarray(np.round(data * 255).astype(np.uint8), mode="RGBA")


def build_master():
    im = Image.open(SRC).convert("RGBA")
    # кроп по фактическим границам через альфа-bbox (углы плитки уже прозрачные),
    # а не «на глаз»: каждый лишний ресемплинг мастера теряет качество.
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    # добиваем до квадрата прозрачными полями, центрируя (не растягиваем!).
    w, h = im.size
    s = max(w, h)
    if (w, h) != (s, s):
        sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        sq.paste(im, ((s - w) // 2, (s - h) // 2))
        im = sq
    im.save(MASTER)
    return im


def main():
    master = build_master()
    frames = []
    for s in SIZES:
        frames.append(resize_linear(master, s, SHARPEN.get(s)))
    # сохраняем ВСЕ наши кадры в .ico: base = самый большой, остальные append.
    frames_by_size = sorted(frames, key=lambda im: im.size[0])
    base = frames_by_size[-1]
    base.save(ICO, format="ICO", sizes=[(f.size[0], f.size[1]) for f in frames_by_size],
              append_images=frames_by_size[:-1])
    print("MASTER", master.size, "->", MASTER)
    print("ICO sizes:", [f.size[0] for f in frames_by_size], "->", ICO)
    print("MAKE_ICON_OK")


if __name__ == "__main__":
    main()
