"""Emissão de DC-e (Declaração de Conteúdo Eletrônica, modelo 68 / chave modelo 99).

Perfil "Marketplace" (tpEmit=1): a MIG assina com o A1 do CNPJ dela, por conta e ordem do
vendedor pessoa física (CPF, remetente). Reaproveita a infra de NF-e (assinatura A1, mTLS)
do pacote `services.fiscal.sefaz`.

Módulos:
  chave_dce      — chave de acesso 44 díg. modelo 99 (CNPJ = assinante).
  xml_builder_dce — monta o XML infDCe conforme o leiaute SVRS (Anexo I).
  (próximos)     — dce_client (WS SVRS), dace (PDF), dce_service (orquestra).
"""
