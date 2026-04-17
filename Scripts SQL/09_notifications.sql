-- ============================================================
-- MIG ECOMMERCE – Script 09: Notificações
-- ============================================================

CREATE TABLE notifications (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id  NUMBER          NOT NULL,
    type            VARCHAR2(50),       -- stock_alert | price_change | new_order | order_cancelled | return_* | subscription_overdue
    title           VARCHAR2(200)   NOT NULL,
    body            VARCHAR2(1000),
    reference_type  VARCHAR2(50),       -- 'order' | 'return' | 'product'
    reference_id    NUMBER,
    is_read         NUMBER(1)       DEFAULT 0 NOT NULL
                        CONSTRAINT chk_notif_read CHECK (is_read IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_notif_dropshipper FOREIGN KEY (dropshipper_id) REFERENCES users(id)
);

-- Critical index for topbar bell unread count + notification list
CREATE INDEX idx_notifications_ds ON notifications(dropshipper_id, is_read, created_at DESC);
