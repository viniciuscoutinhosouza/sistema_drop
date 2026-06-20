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
