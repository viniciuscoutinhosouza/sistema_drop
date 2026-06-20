"""CAPTCHA solver integration (CapSolver).

- Detecta reCAPTCHA / hCaptcha na página
- Resolve via CapSolver API (token-based)
- Injeta token e tenta continuar

API key vem do Windows Credential Manager via secrets.py
Naming: <SERVICE_NAME> / CAPSOLVER_API_KEY
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

from plugins_src._shared.secrets import get_secret


CAPSOLVER_BASE_URL = "https://api.capsolver.com"


@dataclass
class CaptchaTarget:
    kind: str  # "recaptcha" | "hcaptcha"
    website_url: str
    website_key: str


def _now() -> float:
    return time.time()


def _log(log: Optional[Callable[[str], None]], msg: str) -> None:
    try:
        if log:
            log(msg)
    except Exception:
        pass


def _extract_key_from_iframe_src(src: str) -> Optional[str]:
    if not src:
        return None
    try:
        if "k=" in src:
            return src.split("k=")[1].split("&")[0]
    except Exception:
        return None
    return None


def detect_captcha(page) -> Optional[CaptchaTarget]:
    """Detecta captcha e extrai sitekey."""
    url = getattr(page, "url", "") or ""

    # reCAPTCHA: widget explícito
    try:
        el = page.locator(".g-recaptcha").first
        if el.count() > 0:
            key = (el.get_attribute("data-sitekey") or "").strip()
            if key:
                return CaptchaTarget(kind="recaptcha", website_url=url, website_key=key)
    except Exception:
        pass

    # reCAPTCHA: iframe
    try:
        iframe = page.locator("iframe[src*='recaptcha']").first
        if iframe.count() > 0:
            src = (iframe.get_attribute("src") or "").strip()
            key = _extract_key_from_iframe_src(src)
            if key:
                return CaptchaTarget(kind="recaptcha", website_url=url, website_key=key)
    except Exception:
        pass

    # hCaptcha
    try:
        hdiv = page.locator("[data-sitekey][data-callback][class*='h-captcha'], [data-sitekey].h-captcha").first
        if hdiv.count() > 0:
            key = (hdiv.get_attribute("data-sitekey") or "").strip()
            if key:
                return CaptchaTarget(kind="hcaptcha", website_url=url, website_key=key)
    except Exception:
        pass

    try:
        iframe = page.locator("iframe[src*='hcaptcha.com']").first
        if iframe.count() > 0:
            src = (iframe.get_attribute("src") or "").strip()
            if "sitekey=" in src:
                key = src.split("sitekey=")[1].split("&")[0]
                if key:
                    return CaptchaTarget(kind="hcaptcha", website_url=url, website_key=key)
    except Exception:
        pass

    return None


def _capsolver_create_task(client_key: str, task: dict) -> Optional[str]:
    r = requests.post(f"{CAPSOLVER_BASE_URL}/createTask",
                      json={"clientKey": client_key, "task": task}, timeout=30)
    j = r.json()
    if j.get("errorId") != 0:
        return None
    return j.get("taskId")


def _capsolver_poll(client_key: str, task_id: str, *, max_wait_s: int = 120, poll_s: float = 5.0) -> Optional[dict]:
    t0 = _now()
    while _now() - t0 < max_wait_s:
        r = requests.post(f"{CAPSOLVER_BASE_URL}/getTaskResult",
                          json={"clientKey": client_key, "taskId": task_id}, timeout=30)
        j = r.json()
        if j.get("errorId") != 0:
            return None
        if j.get("status") == "ready":
            return j.get("solution")
        time.sleep(poll_s)
    return None


def solve_capsolver(target: CaptchaTarget, *, max_wait_s: int = 120,
                    log: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Resolve captcha via CapSolver. Retorna token ou None."""
    client_key = get_secret("CAPSOLVER_API_KEY")
    if not client_key:
        _log(log, "[captcha] missing CAPSOLVER_API_KEY")
        return None

    if target.kind == "recaptcha":
        task = {"type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": target.website_url, "websiteKey": target.website_key}
        token_field = "gRecaptchaResponse"
    elif target.kind == "hcaptcha":
        task = {"type": "HCaptchaTaskProxyLess",
                "websiteURL": target.website_url, "websiteKey": target.website_key}
        token_field = "token"
    else:
        return None

    _log(log, f"[captcha] createTask kind={target.kind}")
    task_id = _capsolver_create_task(client_key, task)
    if not task_id:
        _log(log, "[captcha] createTask failed")
        return None

    _log(log, f"[captcha] polling taskId={task_id}")
    sol = _capsolver_poll(client_key, task_id, max_wait_s=max_wait_s)
    if not sol:
        _log(log, "[captcha] poll timeout/fail")
        return None

    token = (sol.get(token_field) or "").strip() if isinstance(sol, dict) else ""
    if not token:
        _log(log, "[captcha] empty token")
        return None

    _log(log, "[captcha] token received")
    return token


def inject_token(page, *, kind: str, token: str, log: Optional[Callable[[str], None]] = None) -> bool:
    """Injeta token de captcha resolvido na textarea oculta."""
    token = str(token or "").strip()
    if not token:
        return False

    if kind == "recaptcha":
        name = "g-recaptcha-response"
    elif kind == "hcaptcha":
        name = "h-captcha-response"
    else:
        return False

    js = """
    (kind, name, token) => {
      const sel = `textarea[name='${name}'], textarea#${name}`;
      let ta = document.querySelector(sel);
      if (!ta) {
        ta = document.createElement('textarea');
        ta.name = name;
        ta.id = name;
        ta.style.width = '1px';
        ta.style.height = '1px';
        ta.style.position = 'fixed';
        ta.style.left = '-1000px';
        ta.style.top = '-1000px';
        document.body.appendChild(ta);
      }
      ta.value = token;
      ta.innerHTML = token;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));

      try {
        if (kind === 'recaptcha' && typeof grecaptcha !== 'undefined') {
          try { grecaptcha.getResponse = () => token; } catch(e) {}
        }
      } catch(e) {}

      try {
        const challengeIframes = document.querySelectorAll('iframe[src*="recaptcha/api2/bframe"]');
        challengeIframes.forEach(iframe => {
          iframe.style.display = 'none';
          iframe.style.visibility = 'hidden';
        });
        const overlays = document.querySelectorAll('div[style*="z-index: 2000000000"]');
        overlays.forEach(overlay => overlay.remove());
      } catch(e) {}

      return { ok: true, injected: true, challengeClosed: true };
    }
    """

    try:
        page.evaluate(js, [kind, name, token])
        _log(log, f"[captcha] injected {kind} token")
        return True
    except Exception as e:
        _log(log, f"[captcha] inject failed: {e}")
        return False


def click_recaptcha_checkbox(page, *, log: Optional[Callable[[str], None]] = None) -> bool:
    """Click no checkbox 'Sou humano' do reCAPTCHA. 3 estratégias com fallback."""
    try:
        frame_loc = page.frame_locator("iframe[src*='recaptcha/api2/anchor']")

        try:
            anchor = frame_loc.locator("#recaptcha-anchor").first
            if anchor.count() > 0:
                checked = (anchor.get_attribute("aria-checked") or "").strip().lower()
                if checked == "true":
                    return True
        except Exception:
            pass

        target = frame_loc.locator(".recaptcha-checkbox").first
        if target.count() == 0:
            target = frame_loc.locator(".recaptcha-checkbox-border").first
        if target.count() == 0:
            return False

        # 1) Click normal
        try:
            target.click(timeout=8000)
            page.wait_for_timeout(500)
            return True
        except Exception:
            pass

        # 2) Force click
        try:
            target.click(timeout=8000, force=True)
            page.wait_for_timeout(500)
            return True
        except Exception:
            pass

        # 3) Mouse click no centro
        try:
            bb = target.bounding_box()
            if bb:
                cx = bb["x"] + (bb["width"] / 2)
                cy = bb["y"] + (bb["height"] / 2)
                page.mouse.click(cx, cy)
                page.wait_for_timeout(500)
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False


def has_recaptcha_challenge(page) -> bool:
    """Detecta se o desafio visual (bframe) está presente."""
    try:
        loc = page.locator("iframe[src*='recaptcha/api2/bframe']").first
        return loc.count() > 0
    except Exception:
        return False


def maybe_solve_captcha(page, *, attempts: int = 2, max_wait_s: int = 120,
                        log: Optional[Callable[[str], None]] = None) -> bool:
    """Detecta + click checkbox + resolve + injeta. Safe to call multiple times."""
    checkbox_already_clicked = False

    for _i in range(max(1, int(attempts or 1))):
        tgt = detect_captcha(page)
        if not tgt:
            return False

        _log(log, f"[captcha] detected kind={tgt.kind}")

        if tgt.kind == "recaptcha" and not checkbox_already_clicked:
            click_recaptcha_checkbox(page, log=log)
            checkbox_already_clicked = True
            if not detect_captcha(page):
                return True

        token = solve_capsolver(tgt, max_wait_s=max_wait_s, log=log)
        if not token:
            continue

        if inject_token(page, kind=tgt.kind, token=token, log=log):
            try:
                page.wait_for_timeout(1500)
            except Exception:
                time.sleep(1.5)
            if not detect_captcha(page):
                return True
            return True

    return False
