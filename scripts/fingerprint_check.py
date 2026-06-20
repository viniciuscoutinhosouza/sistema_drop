"""Validação rápida de anti-detect do Camoufox.

Uso:
  python scripts/fingerprint_check.py
  python scripts/fingerprint_check.py --auto --wait 25

O script abre os principais sites de detecção em sequência, espera
o tempo configurado para os scripts rodarem, e salva um screenshot
de cada um. Depois confere os screenshots em output/fingerprint_*/
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
from pathlib import Path

from camoufox.sync_api import Camoufox

URLS = [
    "https://abrahamjuliot.github.io/creepjs/",
    "https://creepjs.org/",
    "https://bot.sannysoft.com/",
    "https://bot.incolumitas.com/",
    "https://arh.antoinevastel.com/bots/areyouheadless",
    "https://fingerprint-scan.com/",
    "https://www.browserscan.net/bot-detection",
    "https://pixelscan.net/bot-check",
    "https://coveryourtracks.eff.org/kcarter?aat=1",
    "https://amiunique.org/fingerprint",
    "https://demo.fingerprint.com/playground",
    "https://browserleaks.com/tls",
]


def _safe_name(url: str) -> str:
    s = url.replace("https://", "").replace("http://", "")
    s = s.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_")
    s = "".join(ch for ch in s if ch.isalnum() or ch in "._-")
    return s[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--wait", type=int, default=20)
    ap.add_argument("--user-data-dir", default=str(Path("browser_profile") / "camoufox"))
    ap.add_argument("--auto", action="store_true",
                    help="Sem pausa entre sites (só espera --wait segundos)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    out_dir = Path(args.out) if args.out else repo_root / "output" / "fingerprint_camoufox" / _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    user_data_dir = Path(args.user_data_dir)
    if not user_data_dir.is_absolute():
        user_data_dir = repo_root / user_data_dir
    user_data_dir.mkdir(parents=True, exist_ok=True)

    print(f"[camoufox] user_data_dir: {user_data_dir}")
    print(f"[camoufox] output_dir:   {out_dir}")
    print("[camoufox] launching (headful, persistent context)…")

    with Camoufox(
        headless=False,
        persistent_context=True,
        user_data_dir=str(user_data_dir),
    ) as context:
        for i, url in enumerate(URLS, start=1):
            print(f"\n[{i:02d}/{len(URLS)}] {url}")
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            except Exception as e:
                print(f"  ! goto error: {e}")

            try:
                page.wait_for_timeout(args.wait * 1000)
            except Exception:
                pass

            name = f"{i:02d}_{_safe_name(url)}.png"
            path = out_dir / name
            try:
                page.screenshot(path=str(path), full_page=True)
                print(f"  [ok] screenshot: {path}")
            except Exception as e:
                print(f"  [err] screenshot: {e}")

            if args.auto:
                try:
                    page.close()
                except Exception:
                    pass
                continue

            input("  Press ENTER to continue to next site… ")
            try:
                page.close()
            except Exception:
                pass

        print("\nDone. Closing Camoufox.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
