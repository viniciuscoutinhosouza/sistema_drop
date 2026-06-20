"""
human_nav.py — Humanização completa de navegação para Playwright.

Fornece classe HumanNav com:
- Movimento de mouse em curva Bézier cúbica com easing ease-in-out
- Cliques com offset aleatório dentro do elemento (não sempre no centro)
- Digitação com ritmo variável e micro-pausas naturais
- Scroll incremental com variação de velocidade
- Delays Gaussianos por contexto
- Rastreamento interno da posição do mouse
- Fallback seguro: se humanização falhar, executa ação direta

Compatível com Playwright Python (sync API).
"""

from __future__ import annotations

import random
import time
from typing import Optional, Tuple

# Perfis de delay por contexto: (média_segundos, desvio_padrão_segundos)
_DELAY_PROFILES = {
    "after_goto":       (1.8, 0.5),
    "after_login":      (2.2, 0.7),
    "between_fields":   (0.6, 0.2),
    "before_click":     (0.25, 0.1),
    "after_click":      (0.4, 0.15),
    "after_fill":       (0.3, 0.1),
    "before_submit":    (1.4, 0.4),
    "reading":          (1.0, 0.4),
    "scroll":           (0.08, 0.03),
    "mouse_step":       (0.03, 0.01),
}


def _gauss_positive(mean: float, std: float, min_val: float = 0.01) -> float:
    while True:
        v = random.gauss(mean, std)
        if v >= min_val:
            return v


def human_delay(context: str = "between_fields") -> None:
    """Pausa Gaussiana baseada no contexto."""
    mean, std = _DELAY_PROFILES.get(context, _DELAY_PROFILES["between_fields"])
    time.sleep(_gauss_positive(mean, std))


def _ease_in_out_cubic(t: float) -> float:
    """Easing cúbico ease-in-out."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


class HumanNav:
    """
    Encapsula interações humanizadas com a página Playwright.

    Usage:
        human = HumanNav(page)
        human.click(locator)
        human.fill(locator, "12345678900")
        human.scroll_to(locator)
    """

    _DEFAULT_X = 683
    _DEFAULT_Y = 100

    def __init__(self, page, viewport_width: int = 1366, viewport_height: int = 768) -> None:
        self._page = page
        self._vw = viewport_width
        self._vh = viewport_height
        self._mx: float = self._DEFAULT_X
        self._my: float = self._DEFAULT_Y

    def _bezier_cubic_point(self, t: float, p0, p1, p2, p3) -> Tuple[float, float]:
        """B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3"""
        mt = 1.0 - t
        x = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0])
        y = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1])
        return x, y

    def move_to(self, dest_x: float, dest_y: float, steps: Optional[int] = None, jitter: int = 3) -> None:
        """Move mouse em curva Bézier cúbica até (dest_x, dest_y)."""
        sx, sy = self._mx, self._my
        dx, dy = dest_x, dest_y

        if steps is None:
            dist = ((dx - sx) ** 2 + (dy - sy) ** 2) ** 0.5
            steps = max(8, min(25, int(dist / 40)))

        mid_x = (sx + dx) / 2
        mid_y = (sy + dy) / 2

        p1 = (mid_x + random.uniform(-80, 80), mid_y + random.uniform(-60, 60))
        p2 = (mid_x + random.uniform(-60, 60), mid_y + random.uniform(-40, 40))
        p0 = (sx, sy)
        p3 = (dx, dy)

        try:
            for i in range(1, steps + 1):
                t_linear = i / steps
                t_eased = _ease_in_out_cubic(t_linear)
                cx, cy = self._bezier_cubic_point(t_eased, p0, p1, p2, p3)

                if i < steps:
                    cx += random.uniform(-jitter, jitter)
                    cy += random.uniform(-jitter, jitter)

                cx = max(0.0, min(float(self._vw - 1), cx))
                cy = max(0.0, min(float(self._vh - 1), cy))

                self._page.mouse.move(cx, cy)
                time.sleep(_gauss_positive(*_DELAY_PROFILES["mouse_step"]))

            self._page.mouse.move(dx, dy)
        except Exception:
            try:
                self._page.mouse.move(dx, dy)
            except Exception:
                pass

        self._mx = dx
        self._my = dy

    def _get_element_rect(self, locator) -> Optional[dict]:
        try:
            el = locator.first if hasattr(locator, "first") else locator
            return el.bounding_box(timeout=3000)
        except Exception:
            return None

    def click(self, locator, *, force: bool = False, hesitate: bool = True) -> None:
        """Click humanizado com offset aleatório + hesitação."""
        try:
            box = self._get_element_rect(locator)
            if box is None:
                raise ValueError("bounding_box retornou None")

            off_x = random.uniform(-box["width"] * 0.35, box["width"] * 0.35)
            off_y = random.uniform(-box["height"] * 0.35, box["height"] * 0.35)

            target_x = box["x"] + box["width"] / 2 + off_x
            target_y = box["y"] + box["height"] / 2 + off_y

            self.move_to(target_x, target_y)

            if hesitate:
                human_delay("before_click")

            if force:
                locator.click(force=True)
            else:
                self._page.mouse.click(target_x, target_y)

            self._mx = target_x
            self._my = target_y

            human_delay("after_click")
        except Exception:
            try:
                locator.click(force=force)
            except Exception:
                pass

    def fill(
        self,
        locator,
        text: str,
        *,
        clear_first: bool = True,
        char_delay_mean: float = 0.09,
        char_delay_std: float = 0.04,
        burst_chance: float = 0.25,
    ) -> None:
        """Preenche campo com ritmo variável + micro-pausas (bursts de 2-5 chars)."""
        try:
            self.click(locator, hesitate=False)

            if clear_first:
                try:
                    self._page.keyboard.press("Control+A")
                    time.sleep(0.05)
                    self._page.keyboard.press("Backspace")
                    time.sleep(0.08)
                except Exception:
                    pass

            if not text:
                return

            i = 0
            while i < len(text):
                burst_size = random.randint(2, 5)
                burst = text[i: i + burst_size]
                i += burst_size

                self._page.keyboard.type(
                    burst,
                    delay=int(_gauss_positive(char_delay_mean, char_delay_std, 0.03) * 1000),
                )

                time.sleep(_gauss_positive(0.05, 0.02))

                if random.random() < burst_chance:
                    time.sleep(_gauss_positive(0.3, 0.12))

            human_delay("after_fill")
        except Exception:
            try:
                el = locator.first if hasattr(locator, "first") else locator
                el.fill(text)
            except Exception:
                pass

    def scroll_to(self, locator, *, extra_down: int = 80) -> None:
        """Scroll incremental humanizado (não scrollIntoView instantâneo)."""
        try:
            box = self._get_element_rect(locator)
            if box is None:
                locator.scroll_into_view_if_needed(timeout=3000)
                return

            current_scroll = self._page.evaluate("window.scrollY")
            target_scroll = current_scroll + box["y"] - self._vh * 0.4 + extra_down
            target_scroll = max(0.0, target_scroll)

            delta = target_scroll - current_scroll
            if abs(delta) < 5:
                return

            steps = random.randint(6, 14)
            step_size = delta / steps

            for i in range(steps):
                vary = _gauss_positive(abs(step_size), abs(step_size) * 0.2)
                actual_step = vary if delta > 0 else -vary
                self._page.evaluate(f"window.scrollBy(0, {actual_step})")
                time.sleep(_gauss_positive(*_DELAY_PROFILES["scroll"]))

            # Overscan reverso (20% chance — humano "passa do ponto e volta")
            if random.random() < 0.2:
                back = random.uniform(15, 40)
                self._page.evaluate(f"window.scrollBy(0, {-back})")
                time.sleep(_gauss_positive(0.15, 0.05))
        except Exception:
            try:
                locator.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

    def idle_jitter(self, duration: float = 1.5, radius: int = 30) -> None:
        """Movimentos pequenos durante espera (simula 'olhar a página')."""
        deadline = time.perf_counter() + duration
        cx, cy = self._mx, self._my

        try:
            while time.perf_counter() < deadline:
                nx = cx + random.uniform(-radius, radius)
                ny = cy + random.uniform(-radius // 2, radius // 2)
                nx = max(0.0, min(float(self._vw - 1), nx))
                ny = max(0.0, min(float(self._vh - 1), ny))

                self._page.mouse.move(nx, ny)
                time.sleep(_gauss_positive(0.2, 0.08))

            self._mx = nx  # type: ignore[possibly-undefined]
            self._my = ny  # type: ignore[possibly-undefined]
        except Exception:
            pass

    def park_mouse(self) -> None:
        """Move mouse pra zona neutra (evita acionar tooltips/hovers)."""
        try:
            park_x = random.uniform(self._vw * 0.1, self._vw * 0.35)
            park_y = random.uniform(self._vh * 0.05, self._vh * 0.2)
            self.move_to(park_x, park_y, jitter=2)
        except Exception:
            pass
