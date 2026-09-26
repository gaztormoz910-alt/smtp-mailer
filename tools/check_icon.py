# -*- coding: utf-8 -*-
"""Проверка иконки: (1) каждый кадр .ico — это уменьшенный тот же мастер, а не
чужая картинка; (2) яркость кадра не просела относительно мастера (эталон яркости
берём попиксельно с мастера, БЕЗ ресемплинга — иначе эталон унёс бы ту же ошибку,
которую ищем). Обязателен негативный контроль: заведомо другая картинка должна
быть ОТВЕРГНУТА, иначе порог пропускал бы что угодно.

Печатает CHECK_ICON_OK и выходит 0 только если все утверждения прошли."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
from make_icon import resize_linear, SIZES  # тот же линейный ресемплинг, что и при сборке

MASTER = os.path.join(REPO, "assets", "Pinion.png")
ICO = os.path.join(REPO, "assets", "Pinion.ico")

DIFF_THRESHOLD = 12.0       # среднее |Δ| по видимым пикселям для «тот же рисунок»
CONTROL_MIN = 40.0          # негативный контроль обязан давать заметно больше
# Яркость проверяем ПО РЕАЛЬНОМУ ДЕФЕКТУ, а не симметричным ±5% к полноразмерному мастеру.
# Замерено на этом мастере: наивное sRGB-уменьшение даёт −11% к мастеру на 16 px (та самая
# ошибка затемнения тонких/контрастных деталей), а корректное линейное — +5.7%. Симметричный
# ±5% ложно завалил бы КОРРЕКТНЫЙ линейный кадр, поэтому:
#  - пол: кадр НЕ темнее мастера более чем на 5% (ловит sRGB-затемнение — тот самый баг);
#  - потолок: кадр НЕ ярче мастера более чем на 15% (ловит грубое переосветление/битую обработку);
#  - на мелких размерах кадр ОБЯЗАН быть ярче наивного sRGB (доказывает, что линейный свет реально
#    применён; при откате на наивный ресемплинг эта проверка падает — регрессия видна).
DARKEN_FLOOR_PCT = 5.0      # ниже этого к мастеру — затемнение
RUNAWAY_CAP_PCT = 15.0      # выше этого к мастеру — переосветление
LINEAR_MARGIN = 2.0         # на размерах ≤ LINEAR_SIZES кадр должен обгонять наивный sRGB на столько уровней
LINEAR_SIZES = 24

fails = []


def luma(arr_rgb):
    return arr_rgb[..., 0] * 0.2126 + arr_rgb[..., 1] * 0.7152 + arr_rgb[..., 2] * 0.0722


def visible_mask(a, thr=10):
    return a > thr


def frame_arr(size):
    ic = Image.open(ICO)
    im = ic.ico.getimage((size, size)).convert("RGBA")
    if im.size != (size, size):
        im = im.resize((size, size), Image.Resampling.LANCZOS)
    return np.asarray(im, dtype=np.float64)


master = Image.open(MASTER).convert("RGBA")
m_arr = np.asarray(master, dtype=np.float64)
# --- эталон средней яркости: попиксельно по мастеру, без ресемплинга ---
m_vis = visible_mask(m_arr[..., 3])
master_luma = float(luma(m_arr[..., :3])[m_vis].mean())

# негативный контроль: инвертированный по цвету мастер (та же альфа) — заведомо «другой»
neg = m_arr.copy()
neg[..., :3] = 255.0 - neg[..., :3]
neg_img = Image.fromarray(neg.astype(np.uint8), "RGBA")

for s in SIZES:
    fr = frame_arr(s)
    ref = np.asarray(resize_linear(master, s), dtype=np.float64)
    m = visible_mask(np.minimum(fr[..., 3], ref[..., 3]))
    if m.sum() == 0:
        fails.append(f"{s}: нет видимых пикселей для сравнения")
        continue
    dev = float(np.abs(fr[..., :3][m] - ref[..., :3][m]).mean())
    if dev > DIFF_THRESHOLD:
        fails.append(f"{s}: кадр расходится с мастером, mean|Δ|={dev:.2f} > {DIFF_THRESHOLD}")

    # негативный контроль на этом же размере
    ref_neg = np.asarray(resize_linear(neg_img, s), dtype=np.float64)
    mn = visible_mask(np.minimum(fr[..., 3], ref_neg[..., 3]))
    dev_neg = float(np.abs(fr[..., :3][mn] - ref_neg[..., :3][mn]).mean()) if mn.sum() else 0.0
    if dev_neg < CONTROL_MIN:
        fails.append(f"{s}: негативный контроль слишком мягкий, mean|Δ|={dev_neg:.2f} < {CONTROL_MIN} (порог пропускал бы что угодно)")

    # яркость кадра: пол (не затемнён), потолок (не переосветлён), и линейность на мелких
    fv = visible_mask(fr[..., 3])
    if fv.sum() == 0:
        fails.append(f"{s}: кадр без видимых пикселей")
        continue
    fl = float(luma(fr[..., :3])[fv].mean())
    dpct = 100.0 * (fl - master_luma) / master_luma
    if dpct < -DARKEN_FLOOR_PCT:
        fails.append(f"{s}: кадр темнее мастера {master_luma:.1f} на {dpct:+.1f}% (< -{DARKEN_FLOOR_PCT}%) — признак sRGB-затемнения")
    if dpct > RUNAWAY_CAP_PCT:
        fails.append(f"{s}: кадр ярче мастера на {dpct:+.1f}% (> +{RUNAWAY_CAP_PCT}%) — переосветление/битая обработка")
    if s <= LINEAR_SIZES:
        naive = np.asarray(master.resize((s, s), Image.Resampling.LANCZOS), dtype=np.float64)
        nv = visible_mask(naive[..., 3])
        naive_luma = float(luma(naive[..., :3])[nv].mean()) if nv.sum() else 0.0
        if not (fl > naive_luma + LINEAR_MARGIN):
            fails.append(f"{s}: кадр {fl:.1f} не ярче наивного sRGB {naive_luma:.1f} — линейный свет не применён (регрессия)")

if fails:
    print("!!! ПРОВАЛЫ ИКОНКИ:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"master_luma={master_luma:.1f}; все {len(SIZES)} кадров совпали с мастером, контроль отвергнут, яркость в норме")
print("CHECK_ICON_OK")
