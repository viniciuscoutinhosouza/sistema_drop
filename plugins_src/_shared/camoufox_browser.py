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

        # AVISO IMPORTANTE: passar --width/--height/--window-position como args CLI
        # do Firefox quebra no Camoufox v135 (instalado aqui) — o Firefox interpreta
        # "1366" como URL IP integer-encoded e abre "https://0.0.5.86". DESATIVADO.
        # O viewport real já é controlado por from_opts["viewport"] logo abaixo.
        # (Bug reproduzido por Vinicius em 2026-06-20 — Sistema Drop.)
        # try:
        #     if not headless:
        #         args = list(from_opts.get('args') or [])
        #         args += ["--width", "1366", "--height", "768"]
        #         args += ["--window-position=0,0"]
        #         from_opts['args'] = args
        # except Exception:
        #     pass

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
                        # Mantém a página default (índice 0) e fecha só as EXTRAS.
                        # Fechar TODAS destrói a janela e quebra context.new_page()
                        # com "window is null" (Quirk #2). Reuse a default no caller.
                        for p in list(getattr(context, 'pages', []) or [])[1:]:
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
