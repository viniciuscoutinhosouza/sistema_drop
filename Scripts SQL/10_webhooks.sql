-- ============================================================
-- MIG ECOMMERCE – Script 10: Webhook Events (Idempotência)
-- ============================================================

CREATE TABLE webhook_events (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform        VARCHAR2(20)    NOT NULL,
    event_id        VARCHAR2(200)   NOT NULL,   -- ID único do evento no marketplace
    event_type      VARCHAR2(100),
    payload         CLOB,                       -- JSON original
    processed       NUMBER(1)       DEFAULT 0 NOT NULL
                        CONSTRAINT chk_we_processed CHECK (processed IN (0,1)),
    error_message   VARCHAR2(1000),
    received_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    processed_at    TIMESTAMP WITH TIME ZONE,
    -- Unique constraint prevents double-processing on retried webhooks
    CONSTRAINT uq_we_platform_event UNIQUE (platform, event_id)
);

CREATE INDEX idx_we_processed ON webhook_events(processed, received_at);
CREATE INDEX idx_we_platform   ON webhook_events(platform, received_at DESC);

-- ============================================================
-- Script de verificação (execute depois de todos os scripts)
-- ============================================================
-- SELECT table_name FROM user_tables ORDER BY table_name;
