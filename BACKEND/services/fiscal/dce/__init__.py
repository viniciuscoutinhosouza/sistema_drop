"""Infra remanescente de DC-e (Declaração de Conteúdo Eletrônica, modelo 99).

⚠️ A EMISSÃO PRÓPRIA via SEFAZ foi REMOVIDA (2026-07-09) — a DC-e passou a ser emitida pelo
emissor do próprio Mercado Livre (link `emissor/omni`), ver ADR-0017 (SUPERSEDED). Sobraram
apenas os módulos ainda usados por features ativas:
  dce_client   — cliente SOAP SVRS (usado pelo teste de certificado central em marketplace_settings).
  signer_cert  — resolução do certificado A1 central do marketplace (PROFILE_MARKETPLACE_DCE).
  dace         — geração do DACE (PDF) a partir de um XML procDCe já autorizado (DACE de legado).
  exceptions   — DceError.
"""
