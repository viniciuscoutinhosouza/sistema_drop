from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _pick_point_in_box(box: Box, *, margin_ratio: float = 0.20) -> Tuple[float, float]:
    """Pick aleatório dentro do box, longe das bordas (evita centro perfeito)."""
    mx = box.width * float(margin_ratio)
    my = box.height * float(margin_ratio)
    x0 = box.x + mx
    x1 = box.x + max(mx, box.width - mx)
    y0 = box.y + my
    y1 = box.y + max(my, box.height - my)

    if x1 <= x0:
        x0 = box.x + box.width * 0.5
        x1 = x0
    if y1 <= y0:
        y0 = box.y + box.height * 0.5
        y1 = y0

    x = random.uniform(x0, x1)
    y = random.uniform(y0, y1)
    return x, y


def _get_or_init_mouse_pos(page) -> Tuple[float, float]:
    pos = getattr(page, "_human_mouse_pos", None)
    if isinstance(pos, tuple) and len(pos) == 2:
        return float(pos[0]), float(pos[1])

    try:
        vp = page.viewport_size
        if vp and vp.get("width") and vp.get("height"):
            start = (float(vp["width"]) - 5.0, float(vp["height"]) - 5.0)
        else:
            start = (1200.0, 700.0)
    except Exception:
        start = (1200.0, 700.0)

    setattr(page, "_human_mouse_pos", start)
    return start


def mouse_park_bottom_right(page) -> None:
    """Move mouse pra zona neutra (canto inferior direito)."""
    try:
        vp = page.viewport_size or {"width": 1366, "height": 768}
        x = float(vp.get("width", 1366)) - 5.0
        y = float(vp.get("height", 768)) - 5.0
        page.mouse.move(int(x), int(y))
        setattr(page, "_human_mouse_pos", (x, y))
    except Exception:
        return


def get_stable_box(
    page,
    locator,
    *,
    retries: int = 3,
    interval_s: float = 0.05,
    tol_px: float = 2.0,
    iframe_selector: str | None = None,
) -> Optional[Box]:
    """Retorna bounding box estável (espera o elemento parar de se mover)."""
    try:
        locator.scroll_into_view_if_needed(timeout=15000)
    except Exception:
        pass

    try:
        locator.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    boxes = []
    for _ in range(max(2, int(retries))):
        try:
            b = locator.bounding_box()
        except Exception:
            b = None
        if not b:
            return None
        boxes.append(Box(float(b["x"]), float(b["y"]), float(b["width"]), float(b["height"])))
        try:
            page.wait_for_timeout(int(float(interval_s) * 1000))
        except Exception:
            pass

    def delta(a: Box, b: Box) -> float:
        return max(abs(a.x - b.x), abs(a.y - b.y), abs(a.width - b.width), abs(a.height - b.height))

    if delta(boxes[-2], boxes[-1]) > tol_px:
        return None

    for bb in boxes[:-1]:
        if delta(bb, boxes[-1]) > tol_px:
            return None

    out = boxes[-1]

    if iframe_selector:
        try:
            fb = page.locator(iframe_selector).first.bounding_box()
            if fb:
                fbox = Box(float(fb["x"]), float(fb["y"]), float(fb["width"]), float(fb["height"]))
                if out.x >= 0 and out.y >= 0 and (out.x + out.width) <= (fbox.width + 5) and (out.y + out.height) <= (fbox.height + 5):
                    out = Box(out.x + fbox.x, out.y + fbox.y, out.width, out.height)
        except Exception:
            pass

    return out


def human_click(page, locator, opts: dict | None = None, *, iframe_selector: str | None = None, label: str = "") -> None:
    """Click humanizado com movimento de mouse + micro pausa + fallback.

    Ativa apenas se opts['use_behavioral_biometrics'] for truthy (default True).
    """
    enabled = True
    try:
        if opts is not None:
            enabled = bool(opts.get("use_behavioral_biometrics", True))
    except Exception:
        enabled = True

    if not enabled:
        locator.click()
        return

    try:
        box = get_stable_box(page, locator, retries=3, interval_s=0.05, tol_px=2.0, iframe_selector=iframe_selector)
        if not box:
            raise RuntimeError("no_box")

        start = _get_or_init_mouse_pos(page)
        target = _pick_point_in_box(box, margin_ratio=0.20)

        # Trajetória: 4-6 pontos intermediários com jitter
        n = random.randint(4, 6)
        pts = []
        for i in range(1, n + 1):
            t = i / (n + 1)
            x = start[0] + (target[0] - start[0]) * t
            y = start[1] + (target[1] - start[1]) * t
            j = random.uniform(-12, 12)
            x += j * (1 - abs(0.5 - t) * 2)
            y -= j * (1 - abs(0.5 - t) * 2)
            pts.append((x, y))

        pts.append(target)

        # Timing: 400-700ms dinâmico com a distância
        d = _dist(start, target)
        base = 400.0 + _clamp(d / 5.0, 0.0, 300.0)
        total_ms = int(_clamp(base + random.uniform(-40, 60), 400.0, 700.0))
        seg_ms = max(20, int(total_ms / max(1, len(pts))))

        cur = start
        for (x, y) in pts:
            steps = int(_clamp(_dist(cur, (x, y)) / 60.0, 3, 12))
            page.mouse.move(int(x), int(y), steps=steps)
            page.wait_for_timeout(seg_ms)
            cur = (x, y)

        page.wait_for_timeout(int(random.uniform(100, 300)))
        page.mouse.down()
        page.wait_for_timeout(int(random.uniform(15, 45)))
        page.mouse.up()

        setattr(page, "_human_mouse_pos", (float(target[0]), float(target[1])))
        mouse_park_bottom_right(page)

    except Exception as e:
        try:
            print(f"[FALLBACK_CLICK]{' '+label if label else ''}: {e}")
        except Exception:
            pass
        locator.click()


def human_idle(page, duration_s: float, opts: dict | None = None) -> None:
    """Pequenos movimentos de mouse durante espera."""
    enabled = True
    try:
        if opts is not None:
            enabled = bool(opts.get("use_behavioral_biometrics", True))
    except Exception:
        enabled = True

    if not enabled:
        return

    try:
        d = float(duration_s or 0)
    except Exception:
        d = 0

    if d <= 3.0:
        return

    try:
        mouse_park_bottom_right(page)
        vp = page.viewport_size or {"width": 1366, "height": 768}
        base_x = float(vp.get("width", 1366)) - 8.0
        base_y = float(vp.get("height", 768)) - 8.0

        steps = int(_clamp(d / 1.2, 2, 6))
        for _ in range(steps):
            dx = random.uniform(-5, 5)
            dy = random.uniform(-5, 5)
            page.mouse.move(int(base_x + dx), int(base_y + dy), steps=4)
            page.wait_for_timeout(int(random.uniform(120, 260)))

        mouse_park_bottom_right(page)
    except Exception:
        return
