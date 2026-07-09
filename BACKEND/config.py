from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Oracle ATP
    ORACLE_USER: str
    ORACLE_PASSWORD: str
    ORACLE_DSN: str  # e.g. "(description=(address=(protocol=tcps)...)"
    ORACLE_WALLET_DIR: str = ""  # path to unzipped Oracle Cloud Wallet folder
    ORACLE_WALLET_PASSWORD: str = ""  # password set when downloading the wallet from Oracle Cloud

    # Pool de conexões + concorrência do AsyncSyncSession (ver ADR-0001).
    # Incidente 2026-07-01: o executor DEFAULT do asyncio (~5 threads em 1 vCPU)
    # esgotou porque jobs do APScheduler ficaram presos num round-trip Oracle SEM
    # timeout → todo request que toca o banco congelou. Correção: executor dedicado
    # ao banco + call_timeout no oracledb. Teto de conexões (POOL_SIZE+MAX_OVERFLOW)
    # deve ficar < 20 (limite de sessões do ATP Always Free).
    ORACLE_POOL_SIZE: int = 8
    ORACLE_MAX_OVERFLOW: int = 7
    # Threads dedicadas ao banco (isoladas do executor de SEFAZ/DANFE/email).
    # ≈ teto de conexões: mais threads que conexões só empilha na fila do pool.
    ORACLE_DB_EXECUTOR_WORKERS: int = 16
    # Aborta um round-trip Oracle pendurado (ms) para a thread não travar "para
    # sempre" numa conexão semi-morta. 0 = sem limite. Folgado o bastante para não
    # abortar batch NFe/relatórios (queries por round-trip, não a transação inteira).
    ORACLE_CALL_TIMEOUT_MS: int = 120000
    # Timeout (s) do ESTABELECIMENTO da conexão TCP com o ATP.
    ORACLE_CONNECT_TIMEOUT_SECONDS: int = 15
    # Executor default do asyncio (SEFAZ/DANFE/email/PDF rodam em asyncio.to_thread) —
    # separado do pool do banco para que uma rajada de emissões NF-e não recongele o DB.
    ASYNCIO_DEFAULT_EXECUTOR_WORKERS: int = 12

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # CORS / Frontend
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    # URL pública do backend — usada para absolutizar URLs de imagens
    # antes de enviar a integrações externas (ML, Shopee) que precisam
    # baixar a imagem por HTTP. Em prod: "https://ecommerce.madeingroup.com.br".
    PUBLIC_BASE_URL: str = ""

    # Mercado Livre
    ML_APP_ID: str = "6712718703908494"
    ML_CLIENT_SECRET: str = ""
    ML_REDIRECT_URI: str = "http://localhost:8000/api/v1/accounts/ml/callback"

    # Shopee
    SHOPEE_PARTNER_ID: str = ""
    SHOPEE_PARTNER_KEY: str = ""
    SHOPEE_REDIRECT_URI: str = "http://localhost:8000/api/v1/accounts/shopee/callback"

    # Platform fee (R$) charged per order payment
    PLATFORM_FEE: float = 2.00

    # Emissão própria de NF-e (SEFAZ direto — mTLS + XMLDSig). Ver ADR e
    # DOCs/guia-implementacao-nfe-oracle.md.
    # Master key (Fernet) p/ cifrar a senha do certificado A1 em repouso no banco.
    # String aleatória longa; NUNCA commitar. Perder a key inutiliza as senhas cifradas.
    NFE_CERT_MASTER_KEY: str = ""
    # Diretório restrito (fora de static/) onde os .pfx das CMIGs ficam no servidor.
    NFE_CERTS_DIR: str = ".secrets/certs"
    # Diretório dos XMLs autorizados (procNFe) — FORA de static/ (dado fiscal/LGPD de
    # terceiros; só baixável pelo endpoint autenticado GET /invoices/{id}/xml).
    NFE_XML_DIR: str = "data/nfe_xml"
    # cabundle ICP-Brasil (produção exige). Vazio → usa o trust store do sistema.
    NFE_ICP_CABUNDLE: str = ""
    # Verificação TLS do servidor da SEFAZ. False só em dev local.
    NFE_VERIFY_SSL: bool = False
    # Distribuição de DFe — Ambiente Nacional (pull das NF-e recebidas pelo CNPJ).
    NFE_DFE_AN_HOMOLOG: str = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
    NFE_DFE_AN_PROD: str = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
    # Timeout (s) das chamadas SOAP à SEFAZ.
    NFE_SEFAZ_TIMEOUT: float = 90.0

    # Coletor ML local (Camoufox) — busca livre que a API do ML bloqueou (403).
    # Roda na máquina do operador (IP residencial), exposta por túnel; o backend
    # chama via HTTP. Vazio/desligado → a Análise de Concorrência degrada para
    # apenas catálogo + highlights (comportamento atual). Ver tools/collector/.
    # Múltiplas máquinas (failover): COLLECTOR_API_URL aceita LISTA separada por
    # vírgula (tenta na ordem; se uma cair/der captcha, tenta a próxima — IPs
    # residenciais diferentes). COLLECTOR_API_TOKEN pode ser 1 token (compartilhado)
    # ou lista alinhada às URLs. Ex.: "https://m1.trycloudflare.com,https://m2.trycloudflare.com".
    COLLECTOR_API_URL: str = ""          # 1+ URLs separadas por vírgula
    COLLECTOR_API_TOKEN: str = ""        # 1 token (compartilhado) ou lista alinhada às URLs
    COLLECTOR_ENABLED: bool = False      # liga a 3ª fonte (busca raspada)
    COLLECTOR_TIMEOUT: float = 960.0     # > SUBPROCESS_TIMEOUT do coletor (900s); cobre deep visit
    COLLECTOR_LIMIT: int = 120           # 120 primeiros por relevância (= DEFAULT_LIMIT do coletor)
    # Nº de anúncios cuja PÁGINA é aberta p/ dados ricos (categoria/ficha/reputação/data).
    # Visita os N MAIS VENDIDOS. Mais = mais lento + maior risco. 20 ≈ 4 min. (= DEFAULT_DEEP_COUNT do coletor)
    COLLECTOR_DEEP_COUNT: int = 20
    # Enriquecimento via API do ML (/items, visitas, reputação) p/ concorrentes.
    # O ML passou a bloquear /items de terceiros (403 PolicyAgent) → DESLIGADO; o
    # estudo opera só com os dados raspados da página de busca. Religar quando/se o
    # ML reabrir a API de itens de concorrentes.
    ML_COMPETITOR_ENRICHMENT: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
