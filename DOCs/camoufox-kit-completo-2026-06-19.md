# Kit Camoufox Anti-Bot — Setup Afinado (passar a outro Claude Code)

> **Origem:** projeto BPFCAR_FINANCEIRAS. Setup de calibração, validado em creepjs.org, bot.incolumitas.com, bot.sannysoft.com, pixelscan, browserscan, fingerprint.com, browserleaks. Passa como humano nos principais sites antibot brasileiros (Itaú, Bradesco, Santander, Banco PAN — todos com proteção Akamai/Cloudflare/Imperva).
>
> **Documento gerado em:** 2026-06-19
> **Camoufox version:** 0.4.11
> **Python:** 3.12+

---

## Instruções para o Claude Code do Vinicius

Cole este documento INTEIRO na conversa com Claude Code. Ele tem tudo o que precisa para reproduzir o setup. Não invente — siga o documento literal. Os comentários no código explicam decisões que custaram caro descobrir.

**Objetivo do Vinicius:** automatizar interações via navegador no Mercado Livre (preencher cadastros, salvar configurações, etc.). Mercado Livre tem proteção anti-bot via Akamai — este setup já foi testado contra Akamai em bancos e passa.

---

## 1. O que é Camoufox e por que NÃO é Playwright puro

Camoufox é um **fork anti-detect do Firefox** mantido por daijro (`https://camoufox.com/`). Ele é controlado via Playwright (`camoufox.sync_api`) mas elimina os marcadores que sites usam para detectar automação:

- `navigator.webdriver` propriedade desativada (Playwright/Selenium puro deixa visível)
- Fingerprint de hardware coerente (CPU, memória, GPU)
- WebGL renderer consistente com OS/GPU declarados
- TLS fingerprint imita Firefox de verdade
- Canvas/AudioContext sem ruído pseudo-aleatório óbvio

**Playwright puro com Firefox NÃO funciona em sites com proteção Akamai/Cloudflare bem configurada.** Camoufox passa.

Mas só a biblioteca não basta — a configuração de runtime é onde mora a calibragem. Este kit entrega essa calibragem.

---

## 2. Pré-requisitos do sistema

- **Sistema operacional:** Windows 10/11 (otimizado para isso). Linux funciona mas o `os="windows"` do Camoufox simula Windows.
- **Python:** 3.12+ (testado em 3.12.7).
- **Conexão internet:** primeira execução baixa o Firefox patcheado (~150 MB).

---

## 3. Dependências (`requirements.txt`)

```
camoufox==0.4.11
playwright>=1.41
playwright-stealth>=2.0.0
```

Após `pip install -r requirements.txt`:

```bash
python -m camoufox fetch
```

Isso baixa o binário do Firefox patcheado. Demora ~2-5 min na primeira vez.

---

## 4. Estrutura de arquivos sugerida

```
projeto/
├── plugins_src/
│   └── _shared/
│       ├── __init__.py
│       ├── camoufox_browser.py   ← CORE (arquivo 1 abaixo)
│       ├── stealthy.py           ← NO-OP wrapper (arquivo 2)
│       └── page_provider.py      ← Helper de uso (arquivo 3)
├── scripts/
│   └── fingerprint_check.py      ← Validação anti-bot (arquivo 4)
├── output/
│   └── browser_profiles/         ← Auto-criada (perfis persistentes)
└── requirements.txt
```

---

## 5. ARQUIVO 1 — `plugins_src/_shared/camoufox_browser.py` (CORE)

> Este é o arquivo que faz tudo acontecer. Não modificar parametrizações marcadas com "SEMPRE".

```python
"""Camoufox Browser - VERSÃO FINAL CONSISTENTE

SOLUÇÃO DEFINITIVA:
- languages: ["pt-BR", "pt"] em TODOS os contextos (CONSISTENTE)
- Aceita que Firefox adiciona "pt" automaticamente
- Viewport < Screen
- Hardware coerente (8 cores SEMPRE)
- webdriver: false (configurable: false)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Tuple

from camoufox.sync_api import Camoufox
from camoufox.utils import launch_options as camo_launch_options


def _norm_viewport(vp: Any) -> Dict[str, int]:
    if isinstance(vp, dict):
        try:
            return {
                "width": int(vp.get("width", 1366)),
                "height": int(vp.get("height", 768)),
            }
        except Exception:
            pass
    return {"width": 1366, "height": 768}


def _is_probably_firefox_ua(ua: str) -> bool:
    s = (ua or "").lower()
    return bool(s) and ("firefox/" in s or "gecko" in s)


def _apply_fingerprint_init_script(context, opts: Dict[str, Any]) -> None:
    """Stealth CONSISTENTE - ['pt-BR', 'pt'] igual ao Worker."""
    
    # SEMPRE usar 8 núcleos (hardware moderno) - ignorar opts
    hc_value = 8
    
    script = f"""
(function() {{
    'use strict';
    
    const HC = {hc_value};  // SEMPRE 8 (hardware moderno)
    const LANGS = ['pt-BR','pt'];  // CONSISTENTE com Worker
    
    // =====================================================
    // MAIN THREAD - Prototype patching
    // =====================================================
    const proto = Object.getPrototypeOf(navigator);
    
    // Hardware Concurrency - SEMPRE 8
    Object.defineProperty(proto, 'hardwareConcurrency', {{
        get: () => HC,
        configurable: false,
        enumerable: true
    }});
    
    // WEBDRIVER: Tentar DELETE primeiro, depois definir
    // Isso remove o rastro da propriedade nativa do Selenium/Playwright
    try {{
        delete proto.webdriver;
    }} catch(e) {{}}
    try {{
        delete Navigator.prototype.webdriver;
    }} catch(e) {{}}
    
    // Agora define como false (não undefined)
    Object.defineProperty(proto, 'webdriver', {{
        get: () => false,
        configurable: false,
        enumerable: true
    }});

    Object.defineProperty(proto, 'deviceMemory', {{
        get: () => 8,
        configurable: false,
        enumerable: true
    }});
    
    // CRÍTICO: ['pt-BR', 'pt'] para consistência com Worker
    Object.defineProperty(proto, 'languages', {{
        get: () => LANGS,
        configurable: false,
        enumerable: true
    }});
    
    Object.defineProperty(proto, 'language', {{
        get: () => 'pt-BR',
        configurable: false,
        enumerable: true
    }});

    // Plugins/MimeTypes: somente um PDF Viewer neutro
    try {{
        const mime = {{ type:'application/pdf', suffixes:'pdf', description:'Portable Document Format' }};
        const plugin = {{
            name:'PDF Viewer',
            filename:'internal-pdf-viewer',
            description:'Portable Document Format',
            length:1,
            0:mime,
            item:(i)=> i===0?mime:null,
            namedItem:(n)=> n==='application/pdf'?mime:null,
            [Symbol.iterator]: function*(){{ yield mime; }}
        }};
        mime.enabledPlugin = plugin;
        const pluginsArr = {{
            length:1,
            0:plugin,
            item:(i)=> i===0?plugin:null,
            namedItem:(n)=> n==='PDF Viewer'?plugin:null,
            refresh:()=>{{}},
            [Symbol.iterator]: function*(){{ yield plugin; }}
        }};
        Object.setPrototypeOf(pluginsArr, PluginArray.prototype);
        Object.defineProperty(navigator,'plugins',{{ get:() => pluginsArr, configurable:false, enumerable:true }});

        const mimesArr = {{
            length:1,
            0:mime,
            item:(i)=> i===0?mime:null,
            namedItem:(n)=> n==='application/pdf'?mime:null,
            [Symbol.iterator]: function*(){{ yield mime; }}
        }};
        Object.setPrototypeOf(mimesArr, MimeTypeArray.prototype);
        Object.defineProperty(navigator,'mimeTypes',{{ get:() => mimesArr, configurable:false, enumerable:true }});
    }} catch(e) {{}}
    
    // =====================================================
    // SERVICE WORKERS - Bloquear
    // =====================================================
    if ('serviceWorker' in navigator) {{
        try {{
            delete navigator.serviceWorker;
        }} catch(e) {{}}
    }}
    
    // Marcar sucesso
    window.__CAMOUFOX_STEALTH_CONSISTENT__ = true;
    console.log('[Camoufox] Stealth CONSISTENTE - HC:', HC, 'Langs:', LANGS);
}})();
"""
    
    context.add_init_script(script)


@contextmanager
def open_camoufox_context(*, bank: str, opts: Dict[str, Any]) -> Iterator[Tuple[Any, Dict[str, Any]]]:
    """Open Camoufox context com configurações CONSISTENTES."""

    bank = (bank or "").strip().lower() or "default"

    headless = bool(opts.get("headless", True))
    locale = "pt-BR"
    timezone_id = "America/Sao_Paulo"

    # Aceitar que Camoufox adiciona 'pt' (isso é consistente com Workers)
    locales = ["pt-BR", "pt"]

    camoufox_config = opts.get("camoufox_config")
    if not isinstance(camoufox_config, dict):
        camoufox_config = {}

    # Viewport MENOR que screen
    viewport = {"width": 1366, "height": 768}

    user_agent = str(opts.get("user_agent") or "").strip()
    if user_agent and not _is_probably_firefox_ua(user_agent):
        user_agent = ""

    slot = int(opts.get("maquina_slot") or 0)
    use_persistent = bool(opts.get("use_persistent_profile", True))

    suffix_override = str(opts.get("profile_suffix") or "").strip()

    user_data_dir: Optional[str] = None
    if use_persistent:
        base = str(opts.get("browser_profile_dir", "output/browser_profiles"))
        suffix = suffix_override or (f"slot_{slot}" if slot > 0 else "default")
        user_data_dir = os.path.join(base, bank, suffix)
        os.makedirs(user_data_dir, exist_ok=True)

        try:
            keep_restore = bool(opts.get('keep_session_restore', False))
            if not keep_restore and user_data_dir:
                import glob
                for pat in (
                    "sessionstore.jsonlz4",
                    "sessionCheckpoints.json",
                    "sessionstore-backups\\*.jsonlz4",
                    "sessionstore-backups\\*.baklz4",
                    "sessionstore-backups\\*.recoverylz4",
                    "sessionstore-backups\\*.lz4",
                ):
                    for fp in glob.glob(os.path.join(user_data_dir, pat)):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
        except Exception:
            pass

    meta = {
        "persistent": use_persistent,
        "user_data_dir": user_data_dir,
        "locale": locale,
        "locales": locales,
        "timezone_id": timezone_id,
    }

    # Accept-Language com pt-BR e pt
    extra_http_headers = {
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    firefox_user_prefs = opts.get("firefox_user_prefs")
    if not isinstance(firefox_user_prefs, dict):
        firefox_user_prefs = None

    # Hardware coerente - SEMPRE 8 (hardware moderno)
    hc_value = 8
    
    fp = dict(firefox_user_prefs or {})
    fp.update({
        "dom.maxHardwareConcurrency": hc_value,
        "intl.accept_languages": "pt-BR,pt",
        "intl.locale.requested": "pt-BR",
        "dom.serviceWorkers.enabled": False,
        "dom.webdriver.enabled": False,
        "privacy.resistFingerprinting": False,
        "privacy.trackingprotection.enabled": False,
        "dom.ipc.processCount": hc_value,
    })
    firefox_user_prefs = fp

    # Disable proxy
    try:
        allow_proxy = bool(opts.get('allow_proxy', False))
        if not allow_proxy:
            fp = dict(firefox_user_prefs or {})
            fp.update({
                "network.proxy.type": 0,
                "network.proxy.autoconfig_url": "",
                "network.proxy.no_proxies_on": "",
                "network.proxy.http": "",
                "network.proxy.http_port": 0,
                "network.proxy.ssl": "",
                "network.proxy.ssl_port": 0,
                "network.proxy.socks": "",
                "network.proxy.socks_port": 0,
                "network.proxy.socks_version": 5,
                "network.proxy.share_proxy_settings": True,
            })
            firefox_user_prefs = fp
    except Exception:
        pass

    i_know = bool(headless and camoufox_config) or bool(camoufox_config)

    main_world_eval = None
    try:
        if "main_world_eval" in opts:
            main_world_eval = bool(opts.get("main_world_eval"))
    except Exception:
        main_world_eval = None

    if use_persistent:
        from_opts = camo_launch_options(
            headless=headless,
            os="windows",
            locale=locales,
            timezone_id=timezone_id,
            user_data_dir=user_data_dir,
            config=camoufox_config,
            i_know_what_im_doing=True if i_know else None,
            main_world_eval=main_world_eval,
        )

        # AVISO IMPORTANTE: a linha abaixo (passar --width/--height/--window-position
        # como args CLI do Firefox) FUNCIONA neste setup específico mas causou bug
        # em outro projeto Tributário com Camoufox versão diferente — Firefox
        # interpretou "1366" como URL IP integer-encoded "0.0.5.86".
        # Se aparecer esse bug ao testar, REMOVA o bloco try/except abaixo.
        # O viewport real é controlado pelo from_opts["viewport"] mais abaixo.
        try:
            if not headless:
                args = list(from_opts.get('args') or [])
                args += ["--width", "1366", "--height", "768"]
                args += ["--window-position=0,0"]
                from_opts['args'] = args
        except Exception:
            pass

        from_opts["locale"] = locale
        from_opts["timezone_id"] = timezone_id
        from_opts["viewport"] = viewport
        if user_agent:
            from_opts["user_agent"] = user_agent
        from_opts["extra_http_headers"] = extra_http_headers
        
        if firefox_user_prefs:
            fp = dict(from_opts.get("firefox_user_prefs") or {})
            fp.update(firefox_user_prefs)
            from_opts["firefox_user_prefs"] = fp

        try:
            fp = dict(from_opts.get("firefox_user_prefs") or {})
            allow_proxy = bool(opts.get('allow_proxy', False))
            if not allow_proxy:
                fp.update({
                    "network.proxy.type": 0,
                    "browser.startup.page": 0,
                    "browser.startup.homepage": "about:blank",
                    "browser.sessionstore.resume_from_crash": False,
                    "browser.sessionstore.resume_session_once": False,
                })
            from_opts["firefox_user_prefs"] = fp
        except Exception:
            pass

        try:
            with Camoufox(
                persistent_context=True,
                user_data_dir=user_data_dir,
                from_options=from_opts,
            ) as context:
                _apply_fingerprint_init_script(context, opts)
                
                try:
                    if not headless:
                        for p in list(getattr(context, 'pages', []) or []):
                            try:
                                p.close()
                            except Exception:
                                pass
                except Exception:
                    pass

                yield context, meta
            return
        except Exception as e:
            msg = str(e)
            if "launch_persistent_context" not in msg:
                raise

            # Fallback non-persistent
            with Camoufox(
                headless=headless,
                os="windows",
                locale=locales,
                firefox_user_prefs=firefox_user_prefs,
                config=camoufox_config,
            ) as browser:
                context = browser.new_context(
                    # NÃO passar locale= aqui! O browser-level locale já governa
                    timezone_id=timezone_id,
                    viewport=viewport,
                    user_agent=user_agent or None,
                    extra_http_headers=extra_http_headers,
                )
                _apply_fingerprint_init_script(context, opts)
                try:
                    meta2 = dict(meta)
                    meta2["persistent"] = False
                    meta2["user_data_dir"] = None
                    yield context, meta2
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass
            return

    # Non-persistent
    with Camoufox(
        headless=headless,
        os="windows",
        locale=locales,
        firefox_user_prefs=firefox_user_prefs,
        config=camoufox_config,
    ) as browser:
        context = browser.new_context(
            # NÃO passar locale= aqui! O browser-level locale já governa
            # para TODOS os contextos (main + workers) = CONSISTENTE
            timezone_id=timezone_id,
            viewport=viewport,
            user_agent=user_agent or None,
            extra_http_headers=extra_http_headers,
        )
        
        _apply_fingerprint_init_script(context, opts)
        
        try:
            yield context, meta
        finally:
            try:
                context.close()
            except Exception:
                pass
```

---

## 6. ARQUIVO 2 — `plugins_src/_shared/stealthy.py` (NO-OP wrapper)

> Existe só pra compatibilidade. Tudo é feito no arquivo 1.

```python
"""
Stealth minimalista - NÃO sobrescreve o que camoufox_browser.py já faz.

IMPORTANTE:
  - camoufox_browser.py aplica o init script principal
  - Este módulo é NO-OP por padrão (nada faz)
  - Mantido para compatibilidade com imports existentes

NÃO adicione init script aqui — duplicação causa detecção.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_LANGS = ["pt-BR", "pt"]
DEFAULT_HW = 8


def apply_stealth_context_sync(context: Any, opts: Optional[Dict[str, Any]] = None) -> None:
    if opts is not None and not opts.get("use_stealth", True):
        return
    # NÃO aplicar init script aqui - já feito em camoufox_browser.py
    log.debug("[stealthy] stealth aplicado via camoufox_browser.py (no-op aqui)")


def apply_stealth_sync(page: Any, opts: Optional[Dict[str, Any]] = None) -> None:
    if opts is not None and not opts.get("use_stealth", True):
        return
    log.debug("[stealthy] stealth aplicado via camoufox_browser.py (no-op aqui)")


apply_stealth_to_context = apply_stealth_context_sync
apply_stealth_to_page = apply_stealth_sync


__all__ = [
    "apply_stealth_context_sync",
    "apply_stealth_sync",
    "apply_stealth_to_context",
    "apply_stealth_to_page",
    "DEFAULT_LANGS",
    "DEFAULT_HW",
]
```

---

## 7. ARQUIVO 3 — `plugins_src/_shared/page_provider.py` (helper de uso)

```python
"""Shared page/context provider.

Permite que múltiplos scripts usem um contexto Camoufox pré-aberto OU
abram seu próprio contexto via open_camoufox_context.

REGRA:
- Se ctx['runtime']['page'] existe, USA e NÃO fecha
- Caso contrário, abre próprio contexto e CONTROLA fechamento
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Tuple

from plugins_src._shared.camoufox_browser import open_camoufox_context


@contextmanager
def provide_page(*, bank: str, ctx: Dict[str, Any]) -> Iterator[Tuple[Any, Any, bool]]:
    """Yield (context, page, owned).

    owned=True  → provider criou; vai fechar.
    owned=False → veio de ctx['runtime']; NÃO fechar.
    
    IMPORTANTE: stealth já foi aplicado pelo camoufox_browser.py.
    NÃO reaplicar via page.evaluate() — causa conflito.
    """

    opts = (ctx.get("opts") or {}) if isinstance(ctx, dict) else {}
    runtime = (ctx.get("runtime") or {}) if isinstance(ctx, dict) else {}

    page = runtime.get("page")
    if page is not None:
        try:
            context = page.context
        except Exception:
            context = runtime.get("context")
        yield context, page, False
        return

    with open_camoufox_context(bank=bank, opts=opts) as (context, _meta):
        page = context.new_page()
        yield context, page, True
```

---

## 8. ARQUIVO 4 — `scripts/fingerprint_check.py` (validação anti-bot)

> Rode este script ANTES de tentar Mercado Livre. Ele tira screenshots dos principais sites de detecção de bot e te mostra se o setup está passando.

```python
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
```

---

## 9. Princípios não-negociáveis (regras descobertas em calibração)

Estas regras vêm do CLAUDE.md do projeto BPFCAR_FINANCEIRAS. **Quebrar qualquer uma re-introduz detecção.**

1. **NUNCA passar `locale=` em `browser.new_context()`** — o locale do browser (passado em `Camoufox(locale=...)`) governa TODOS os contextos. Re-passar em `new_context()` cria inconsistência entre Main thread e Workers, que sites detectam.

2. **`hardwareConcurrency` SEMPRE = 8** — hardware moderno típico. Variar entre execuções é o primeiro sinal de fingerprint instável que sites usam para "lembrar" do bot.

3. **`webdriver` SEMPRE com `configurable: false`** — definir como `false` mas com `configurable: true` ainda é detectável (sites tentam `delete navigator.webdriver` e veem se volta).

4. **NUNCA habilitar `privacy.resistFingerprinting`** — paradoxalmente, esta config do Firefox MUDA o fingerprint de forma muito específica que sites antibot detectam como "Firefox em modo paranoid = automação".

5. **Languages SEMPRE `["pt-BR", "pt"]`** — Camoufox/Firefox adiciona "pt" automaticamente em Workers. Se Main thread tem só "pt-BR", há inconsistência detectável.

6. **Viewport MENOR que screen** — `viewport={1366, 768}` em telas 1920×1080 é configuração comum de usuário. Viewport = screen é raro e detectável.

7. **NÃO reaplicar stealth via `page.evaluate()`** — o init script via `context.add_init_script()` roda ANTES de qualquer documento carregar. Reaplicar via `page.evaluate()` cria duplicação que alguns sites detectam.

8. **Plugins/MimeTypes: SÓ PDF Viewer neutro** — Firefox não tem plugins de verdade, mas sites esperam algum array. PDF Viewer é o default seguro.

9. **Service Workers bloqueados** — sites antibot modernos usam Service Workers pra coletar fingerprint adicional. Bloquear é mais limpo.

10. **Perfis persistentes por bank/site** — `user_data_dir` por fonte. Cookies, localStorage, IndexedDB se acumulam realisticamente. Site lembra de "usuário recorrente" = pontuação anti-bot mais baixa.

---

## 10. Lições aprendidas (quirks)

### Quirk #1 — Args CLI do Firefox

Algumas versões do Camoufox passam `--width 1366 --height 768 --window-position=0,0` como args CLI e funciona. **Outras versões interpretam "1366" como URL IP integer-encoded e abrem `https://0.0.5.86`.** Se acontecer, REMOVA o bloco `try/except` que adiciona esses args (está marcado no arquivo 1 com `AVISO IMPORTANTE`).

### Quirk #2 — Persistent context exige reuso da página default

Em modo `persistent_context=True`, o Camoufox já abre uma `about:blank` default. Tentar `context.new_page()` antes da default estabilizar pode dar erro `window is null`. O código do arquivo 1 fecha as pages extras em headful pra evitar isso.

### Quirk #3 — Fingerprint duplo via page.evaluate

Antes, o código aplicava o init script DUAS vezes (uma via `add_init_script`, outra via `page.evaluate`). Sites detectavam a duplicação como "scripts injetados". Solução: aplicar uma única vez via `add_init_script`. Por isso o `stealthy.py` é NO-OP.

### Quirk #4 — Locale em new_context() quebra Workers

Setup antigo passava `locale="pt-BR"` em `new_context()`. Isso fazia o Main thread reportar `["pt-BR"]` mas os Web Workers reportarem `["pt-BR", "pt"]` (porque o browser-level locale adiciona "pt"). Inconsistência detectada por CreepJS. **Solução:** governar locale só em `Camoufox(locale=["pt-BR", "pt"])`, nunca em `new_context()`.

### Quirk #5 — sessionstore lixo após crash

Firefox tenta restaurar sessão após crash. Em automação, isso polui o perfil persistente com tabs antigas. O código apaga `sessionstore.jsonlz4` e variantes no startup. Sem isso, primeira execução após crash mostra abas indevidas.

---

## 11. Como usar (exemplo mínimo)

```python
# main.py
from plugins_src._shared.camoufox_browser import open_camoufox_context

opts = {
    "headless": False,           # True quando estiver tudo OK
    "use_persistent_profile": True,
    "browser_profile_dir": "output/browser_profiles",
    "profile_suffix": "ml_principal",  # nome do perfil
}

with open_camoufox_context(bank="mercadolivre", opts=opts) as (context, meta):
    page = context.new_page()
    page.goto("https://www.mercadolivre.com.br/", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    # ... resto da automação aqui
    page.screenshot(path="ml_home.png")
```

Primeiro run vai criar `output/browser_profiles/mercadolivre/ml_principal/` com o perfil. Próximas execuções reusam — cookies/login persistem.

---

## 12. Adaptação para Mercado Livre

Mercado Livre tem proteção Akamai (mesma que bancos brasileiros). Este setup já passa em Akamai. Mas há considerações específicas:

### a) Login

ML pode pedir CAPTCHA no login. Soluções:
- **Manual:** rodar headful, fazer login na mão, deixar perfil persistente. Próximas execuções não pedem mais.
- **Automatizado:** integrar CapSolver ou 2Captcha (não incluído neste kit; tem código de exemplo no projeto BPFCAR_FINANCEIRAS em `captcha_solver.py`).

### b) Comportamento humano

ML detecta cliques muito rápidos ou em coordenadas perfeitamente centralizadas. Para automação realista:
- Insira `page.wait_for_timeout(random.randint(800, 2400))` entre ações
- Use `page.mouse.move(x, y, steps=random.randint(5, 15))` antes de cliques
- Não preencha campos via `page.fill()` direto. Use `Ctrl+A` + `Delete` + `page.keyboard.type(texto, delay=random.randint(80, 180))`

### c) Rate limit

Não fazer muitas requisições em sequência. Mercado Livre tem heurística baseada em volume. Espalhe ações.

### d) User-Agent

Não setar `user_agent` manualmente — o Camoufox gera UA coerente automaticamente. Se setar errado, quebra o fingerprint.

---

## 13. Testes de aceite (antes de declarar pronto)

Antes de rodar contra Mercado Livre de verdade:

1. **Rodar `python scripts/fingerprint_check.py`** e conferir os screenshots em `output/fingerprint_camoufox/AAAAMMDD_HHMMSS/`:
   - **CreepJS:** trust score >= 70%, sem `webdriver: true`, sem flags óbvias
   - **bot.sannysoft.com:** TODOS os checks verdes (Webdriver, Chrome, Permissions, Plugins, Languages, WebGL Vendor, WebGL Renderer)
   - **bot.incolumitas.com:** "Bot detected: No" + score >= 0.7
   - **pixelscan:** "Not a bot" verde

2. **Testar acesso ao Mercado Livre sem login:**
   ```python
   page.goto("https://www.mercadolivre.com.br/", wait_until="domcontentloaded")
   page.wait_for_timeout(5000)
   # Não deve aparecer captcha nem página de bloqueio
   ```

3. **Testar login manual headful** — uma vez funcionando, deixar perfil persistente fazer o resto.

---

## 14. Módulos avançados — TODOS INCLUÍDOS NESTE KIT

Pra Mercado Livre que tem detecção de comportamento humano (não só fingerprint), os módulos abaixo fazem a diferença. Cada um é opcional individualmente, mas a combinação eleva drasticamente a taxa de sucesso em sites com Akamai/Cloudflare avançado.

**Resumo do que cada um faz:**

| Módulo | Propósito | Quando usar |
|---|---|---|
| `secrets.py` | Armazena API keys no Windows Credential Manager | Sempre (base do captcha_solver) |
| `human.py` | Pausas humanas (micro_pause, action_pause, safe_click/fill) | Sempre |
| `biometrics.py` | Movimento de mouse com curva Bézier leve + perfil persistente | Sempre |
| `human_nav.py` | Navegação humanizada COMPLETA (classe HumanNav: clique, fill, scroll, idle) | Quando ML tiver detecção de comportamento |
| `captcha_solver.py` | Detecta e resolve reCAPTCHA/hCaptcha via CapSolver | Quando ML mostrar captcha (login, fluxos sensíveis) |
| `login_errors.py` | Detecta mensagem de erro de credencial inválida | Após qualquer submit de login |
| `step_trace.py` | Telemetria de cada step (duração, status, JSONL) | Debugging e monitoramento |
| `dev_dump.py` | Stub NO-OP (referenciado por human.py — só pra import funcionar) | Sempre (mock) |

---

### 14.A — `requirements.txt` atualizado

Substitua o arquivo do passo 3 por este (adiciona dependências dos módulos avançados):

```
camoufox==0.4.11
playwright>=1.41
playwright-stealth>=2.0.0
requests==2.32.3
keyring==25.6.0
```

---

### 14.B — `plugins_src/_shared/secrets.py`

> Acesso a API keys via Windows Credential Manager. Base do `captcha_solver.py`.

```python
"""Shared secrets access.

Usa Windows Credential Manager via `keyring` para armazenar API keys
localmente. Evita commitar chaves em arquivos junto ao código.

Naming:
- service: FinanceirasFinn (pode renomear pro nome do seu projeto)
- username: <KEY_NAME>

Exemplo: FinanceirasFinn / CAPSOLVER_API_KEY
"""

from __future__ import annotations

from typing import Optional


SERVICE_NAME = "FinanceirasFinn"  # Renomeie pro seu projeto


def get_secret(name: str) -> Optional[str]:
    try:
        import keyring  # type: ignore
        v = keyring.get_password(SERVICE_NAME, str(name))
        return str(v).strip() if v else None
    except Exception:
        return None


def set_secret(name: str, value: str) -> bool:
    try:
        import keyring  # type: ignore
        keyring.set_password(SERVICE_NAME, str(name), str(value))
        return True
    except Exception:
        return False
```

---

### 14.C — `plugins_src/_shared/dev_dump.py` (stub NO-OP)

> O `human.py` referencia este módulo para telemetria opcional. Crie como NO-OP — não interfere em nada.

```python
"""Stub NO-OP. Sem efeito. Mantido apenas para satisfazer imports do human.py."""

from __future__ import annotations
from typing import Any, Dict, Optional


def maybe_dump(page: Any, *, bank: str = "", opts: Optional[Dict[str, Any]] = None) -> None:
    """NO-OP — não faz nada."""
    return
```

---

### 14.D — `plugins_src/_shared/human.py`

> Pausas humanas + helpers `safe_click` / `safe_fill` que esperam visibilidade + delay natural antes da ação.

```python
from __future__ import annotations

import random
from typing import Iterable, Optional

from plugins_src._shared.dev_dump import maybe_dump


def _ms(a: int, b: int) -> int:
    a = int(a)
    b = int(b)
    if b < a:
        a, b = b, a
    return int(random.randint(a, b))


def micro_pause(page, opts: dict, *, fallback_min_ms: int = 120, fallback_max_ms: int = 700) -> None:
    """Jitter curto entre sub-ações.

    Use em vez de sleeps fixos. Pequeno o suficiente pra não dominar runtime,
    mas grande o suficiente pra reduzir padrões idênticos de timing.
    """
    try:
        maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
    except Exception:
        pass

    a = int(opts.get("human_micro_pause_ms_min", fallback_min_ms))
    b = int(opts.get("human_micro_pause_ms_max", fallback_max_ms))
    page.wait_for_timeout(_ms(a, b))


def action_pause(page, opts: dict, *, fallback_min_s: float = 2.0, fallback_max_s: float = 6.0) -> None:
    """Jitter longo após ações grandes (humanos naturalmente pausam aqui)."""
    try:
        maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
    except Exception:
        pass

    a = float(opts.get("human_action_delay_s_min", fallback_min_s))
    b = float(opts.get("human_action_delay_s_max", fallback_max_s))
    if b < a:
        a, b = b, a
    page.wait_for_timeout(int(random.uniform(a, b) * 1000))


def key_delay_ms(opts: dict, *, fallback_min_ms: int = 40, fallback_max_ms: int = 140) -> int:
    return _ms(int(opts.get("human_key_delay_ms_min", fallback_min_ms)),
               int(opts.get("human_key_delay_ms_max", fallback_max_ms)))


def wait_any_visible(locators: Iterable, *, timeout_ms: int = 60000):
    """Retorna o primeiro locator que ficar visível."""
    last = None
    for loc in locators:
        try:
            loc.wait_for(state="visible", timeout=timeout_ms)
            return loc
        except Exception:
            last = loc
            continue
    if last is not None:
        last.wait_for(state="visible", timeout=timeout_ms)
    return last


def safe_click(loc, page=None, opts: Optional[dict] = None, *, timeout_ms: int = 60000) -> None:
    """Click com 'percepção' + pausa humana.

    Regra: assim que o alvo ficar visível (percebido como disponível), aplicamos
    o delay longo (action_pause) e só então clicamos.
    """
    loc.wait_for(state="visible", timeout=timeout_ms)
    if page is not None and opts is not None:
        try:
            maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
        except Exception:
            pass
        action_pause(page, opts)
    loc.click()


def safe_fill(loc, text: str, page=None, opts: Optional[dict] = None, *, timeout_ms: int = 60000) -> None:
    """Fill com 'percepção' + pausa humana (entre campos)."""
    loc.wait_for(state="visible", timeout=timeout_ms)
    if page is not None and opts is not None:
        try:
            maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
        except Exception:
            pass
        action_pause(page, opts)
    loc.fill(text)


def safe_type(page, text: str, *, delay_ms: int = 80) -> None:
    page.keyboard.type(text, delay=int(delay_ms))
```

---

### 14.E — `plugins_src/_shared/biometrics.py`

> Movimentos de mouse com leve curva (não Bézier completa — versão "rápida"). Define `Box` e `human_click` com `get_stable_box` (espera o elemento ficar estável antes de clicar — importante quando UI tem animação).

```python
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
```

---

### 14.F — `plugins_src/_shared/human_nav.py` (HumanNav — RECOMENDADO PARA MERCADO LIVRE)

> Classe `HumanNav` completa com Bézier cúbica + easing + offset aleatório de clique + digitação em bursts + scroll incremental + idle jitter. **Este é o módulo mais sofisticado e o mais útil pra Mercado Livre.**

```python
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
```

---

### 14.G — `plugins_src/_shared/captcha_solver.py`

> Detecta reCAPTCHA/hCaptcha e resolve via CapSolver API. Inclui click no checkbox + injeção de token. Requer `CAPSOLVER_API_KEY` no Windows Credential Manager (ver seção 16).

```python
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
```

---

### 14.H — `plugins_src/_shared/login_errors.py`

> Detecta mensagem de erro de credencial inválida na página. Útil pra abortar fluxo cedo com mensagem clara.

```python
"""Detecta erros de login/credencial em qualquer site PT-BR.

Padrões funcionam para Mercado Livre, bancos, qualquer site que use
linguagem padrão de erro no português.
"""

from __future__ import annotations

import re
from typing import Optional


_DEFAULT_PATTERNS = [
    r"usu[aá]rio\s+ou\s+senha\s+inv[aá]lid",
    r"senha\s+inv[aá]lid",
    r"usu[aá]rio\s+inv[aá]lid",
    r"login\s+inv[aá]lid",
    r"dados\s+inv[aá]lid",
    r"credenciais\s+inv[aá]lid",
    r"n[aã]o\s+foi\s+poss[ií]vel\s+autenticar",
    r"acesso\s+negado",
    r"conta\s+bloqueada",
    r"tentativas\s+excedidas",
]


def detect_login_error_message(page, *, extra_patterns: list[str] | None = None) -> Optional[str]:
    """Procura mensagem de erro visível na página. Retorna texto ou None."""

    pats = list(_DEFAULT_PATTERNS)
    if extra_patterns:
        pats.extend([p for p in extra_patterns if isinstance(p, str) and p.strip()])

    # 1) Busca direta via get_by_text
    for p in pats:
        try:
            loc = page.get_by_text(re.compile(p, re.I))
            if loc.count() > 0:
                try:
                    txt = loc.first.evaluate("el => (el.innerText || el.textContent || '').trim()")
                    txt = (txt or '').strip()
                    if txt:
                        return txt[:300]
                except Exception:
                    return re.sub(r"\s+", " ", loc.first.inner_text()).strip()[:300]
        except Exception:
            continue

    # 2) Fallback: varre body
    try:
        body_txt = page.inner_text("body")
        body_txt_n = re.sub(r"\s+", " ", (body_txt or "")).strip()
        if not body_txt_n:
            return None
        for p in pats:
            if re.search(p, body_txt_n, flags=re.I):
                m = re.search(p, body_txt_n, flags=re.I)
                if not m:
                    continue
                start = max(0, m.start() - 80)
                end = min(len(body_txt_n), m.end() + 120)
                return body_txt_n[start:end].strip()[:300]
    except Exception:
        pass

    return None
```

---

### 14.I — `plugins_src/_shared/step_trace.py`

> Telemetria estruturada (JSONL) de cada step com duração + status. Útil pra debugging e identificar gargalos.

```python
"""Telemetria estruturada de steps de execução.

Emite eventos JSONL com:
- duration_ms: tempo no step
- elapsed_ms: tempo acumulado desde início
- status: start|ok|fail
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional


class StepTracer:
    """Logger estruturado de timing por step."""

    def __init__(self, out_dir: Path, bank: str, *,
                 log_fn: Optional[Callable[[str], None]] = None,
                 filename: Optional[str] = None) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.bank = (bank or "").strip().lower() or "unknown"
        self.log_fn = log_fn
        self._t0 = time.perf_counter()
        self._seq = 0
        self.path = self.out_dir / (filename or f"log_{self.bank}_steps.jsonl")

    def _elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def _emit(self, payload: dict) -> None:
        data = {
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bank": self.bank,
            **payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @contextmanager
    def step(self, name: str, detail: str = "") -> Iterator[None]:
        self._seq += 1
        seq = self._seq
        start = time.perf_counter()
        self._emit({"seq": seq, "step": name, "status": "start",
                    "detail": detail, "elapsed_ms": self._elapsed_ms()})
        if self.log_fn:
            try:
                self.log_fn(f"[step:{seq}] START {name} | elapsed_ms={self._elapsed_ms()} | {detail}")
            except Exception:
                pass
        try:
            yield
            duration_ms = int((time.perf_counter() - start) * 1000)
            elapsed_ms = self._elapsed_ms()
            self._emit({"seq": seq, "step": name, "status": "ok",
                        "detail": detail, "duration_ms": duration_ms, "elapsed_ms": elapsed_ms})
            if self.log_fn:
                try:
                    self.log_fn(f"[step:{seq}] OK {name} | duration_ms={duration_ms} | elapsed_ms={elapsed_ms}")
                except Exception:
                    pass
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            elapsed_ms = self._elapsed_ms()
            self._emit({"seq": seq, "step": name, "status": "fail",
                        "detail": detail, "duration_ms": duration_ms, "elapsed_ms": elapsed_ms,
                        "error": f"{type(e).__name__}: {e}"})
            if self.log_fn:
                try:
                    self.log_fn(f"[step:{seq}] FAIL {name} | duration_ms={duration_ms} | elapsed_ms={elapsed_ms} | {type(e).__name__}: {e}")
                except Exception:
                    pass
            raise
```

---

## 15. Exemplo integrado — Mercado Livre com TODOS os módulos

```python
# main_ml.py — uso completo do kit
from pathlib import Path
from plugins_src._shared.camoufox_browser import open_camoufox_context
from plugins_src._shared.human_nav import HumanNav, human_delay
from plugins_src._shared.captcha_solver import maybe_solve_captcha
from plugins_src._shared.login_errors import detect_login_error_message
from plugins_src._shared.step_trace import StepTracer


def fazer_algo_no_ml(usuario: str, senha: str):
    opts = {
        "headless": False,
        "use_persistent_profile": True,
        "browser_profile_dir": "output/browser_profiles",
        "profile_suffix": "ml_principal",
    }

    tracer = StepTracer(Path("output/traces"), "mercadolivre",
                        log_fn=lambda m: print(m))

    with open_camoufox_context(bank="mercadolivre", opts=opts) as (context, meta):
        page = context.new_page()
        human = HumanNav(page)

        # 1) Acesso inicial
        with tracer.step("goto_ml"):
            page.goto("https://www.mercadolivre.com.br/", wait_until="domcontentloaded")
            human_delay("after_goto")
            human.idle_jitter(duration=1.5)

        # 2) Captcha eventual na home?
        with tracer.step("solve_captcha_if_any"):
            maybe_solve_captcha(page, attempts=2, log=lambda m: print(m))

        # 3) Botão de login
        with tracer.step("click_login_btn"):
            btn_login = page.get_by_role("link", name="Entre")
            human.scroll_to(btn_login)
            human.click(btn_login)

        # 4) Form de login
        with tracer.step("fill_email"):
            email_input = page.get_by_label("E-mail ou telefone")
            human.fill(email_input, usuario)

        with tracer.step("submit_email"):
            btn_next = page.get_by_role("button", name="Continuar")
            human.click(btn_next)
            human_delay("before_submit")

        # 5) Captcha após email?
        with tracer.step("solve_captcha_post_email"):
            maybe_solve_captcha(page, attempts=2, log=lambda m: print(m))

        # 6) Senha
        with tracer.step("fill_password"):
            pass_input = page.get_by_label("Senha")
            human.fill(pass_input, senha)

        with tracer.step("submit_password"):
            btn_login = page.get_by_role("button", name="Entrar")
            human.click(btn_login)
            human_delay("after_login")

        # 7) Erro de credencial?
        with tracer.step("check_login_error"):
            err = detect_login_error_message(page)
            if err:
                print(f"[ERRO] Login falhou: {err}")
                page.screenshot(path="output/login_error.png")
                return False

        # 8) Logado — fazer ação no painel
        with tracer.step("salvar_algo_no_painel"):
            # ... sua lógica específica aqui
            human.idle_jitter(duration=2.0)
            page.screenshot(path="output/ml_logado.png")

        return True


if __name__ == "__main__":
    import os
    sucesso = fazer_algo_no_ml(
        usuario=os.environ.get("ML_USER", ""),
        senha=os.environ.get("ML_PASS", ""),
    )
    print(f"Resultado: {'OK' if sucesso else 'FALHOU'}")
```

---

## 16. Setup do CapSolver (API key)

Se for usar captcha_solver, precisa de uma API key do CapSolver (~$0.80 USD por 1000 captchas resolvidos, créditos pré-pagos).

1. Cadastre em https://capsolver.com/ e adicione crédito (mínimo $5)
2. Obtenha a API key no dashboard
3. Armazene no Windows Credential Manager via terminal Python:

```python
from plugins_src._shared.secrets import set_secret
set_secret("CAPSOLVER_API_KEY", "CAP-XXXXXXXXXXXXXXXXXXXXXXXX")
```

4. Pronto — `captcha_solver.py` lê automaticamente sempre que precisar resolver captcha.

**Importante:** se renomear o `SERVICE_NAME` em `secrets.py` (default `FinanceirasFinn`), use o mesmo nome ao armazenar e ao buscar.

---

## 17. Testes de aceite (antes de Mercado Livre real)

1. **Rodar `python scripts/fingerprint_check.py`** e conferir screenshots:
   - CreepJS trust >= 70%
   - bot.sannysoft.com TODOS verdes
   - bot.incolumitas.com "Bot detected: No"
   - pixelscan "Not a bot"

2. **Testar acesso ML anônimo:**
   ```python
   page.goto("https://www.mercadolivre.com.br/")
   # Não deve aparecer captcha imediato nem página de bloqueio
   ```

3. **Login manual headful 1x** — perfil persistente fica salvo.

4. **Login automatizado headful** com `HumanNav` + `captcha_solver` — confirma fluxo end-to-end.

5. **Headless** só depois de tudo OK em headful.

---

## 18. Estrutura final de arquivos

```
projeto/
├── plugins_src/
│   ├── __init__.py
│   └── _shared/
│       ├── __init__.py
│       ├── camoufox_browser.py    ← CORE (arquivo 1 da seção 5)
│       ├── stealthy.py            ← NO-OP wrapper (arquivo 2 da seção 6)
│       ├── page_provider.py       ← Helper (arquivo 3 da seção 7)
│       ├── secrets.py             ← Credential Manager (14.B)
│       ├── dev_dump.py            ← Stub NO-OP (14.C)
│       ├── human.py               ← Pausas + safe_click/fill (14.D)
│       ├── biometrics.py          ← Mouse com curva leve (14.E)
│       ├── human_nav.py           ← HumanNav classe completa (14.F)
│       ├── captcha_solver.py      ← CapSolver integration (14.G)
│       ├── login_errors.py        ← Detecta erros de login (14.H)
│       └── step_trace.py          ← Telemetria JSONL (14.I)
├── scripts/
│   └── fingerprint_check.py       ← Validação anti-bot (arquivo 4 da seção 8)
├── output/
│   ├── browser_profiles/          ← Auto-criada
│   ├── fingerprint_camoufox/      ← Screenshots de validação
│   └── traces/                    ← JSONL do step_trace
├── main_ml.py                     ← Seu script (exemplo na seção 15)
└── requirements.txt               ← Da seção 14.A
```

---

## 19. Suporte / dúvidas

1. **Primeiro:** rode `fingerprint_check.py`. CreepJS aponta o motivo exato se for detectado.
2. **Segundo:** confira `pip show camoufox` = `0.4.11`.
3. **Terceiro:** sempre teste headful primeiro.
4. **Quarto:** se Mercado Livre mostrar captcha persistente, configure CapSolver (seção 16).
5. **Último:** se nada funcionar, peça pro Fernando o log do CreepJS pra análise.

---

## Apêndice — checklist final do Vinicius

**Setup básico:**
- [ ] Python 3.12+ instalado
- [ ] `pip install -r requirements.txt` executado
- [ ] `python -m camoufox fetch` executado (baixou ~150 MB)
- [ ] Os 11 arquivos do kit copiados em `plugins_src/_shared/`
- [ ] `fingerprint_check.py` copiado em `scripts/`

**Validação:**
- [ ] Rodou `python scripts/fingerprint_check.py` e screenshots estão OK (CreepJS verde, bot.sannysoft todos verdes)
- [ ] Testou acesso ML sem captcha
- [ ] Fez login manual headful 1x (perfil persistente criado)

**CapSolver (opcional, só se aparecer captcha):**
- [ ] Conta criada em https://capsolver.com/
- [ ] Crédito adicionado (mínimo $5)
- [ ] API key armazenada via `set_secret("CAPSOLVER_API_KEY", "...")`

**Produção:**
- [ ] Adapte `main_ml.py` da seção 15 pra sua tarefa específica
- [ ] Teste headful end-to-end
- [ ] Só depois passe pra headless (`opts["headless"] = True`)

Boa!
