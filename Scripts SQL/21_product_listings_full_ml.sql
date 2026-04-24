-- Script 21: Campos completos para publicação ML em product_listings

ALTER TABLE product_listings ADD description_override CLOB;
ALTER TABLE product_listings ADD attributes_json      VARCHAR2(4000);
ALTER TABLE product_listings ADD available_quantity   NUMBER(6)    DEFAULT 1;
ALTER TABLE product_listings ADD item_condition       VARCHAR2(20) DEFAULT 'new';
ALTER TABLE product_listings ADD warranty_type        VARCHAR2(50);
ALTER TABLE product_listings ADD warranty_time        VARCHAR2(20);
ALTER TABLE product_listings ADD shipping_mode        VARCHAR2(20) DEFAULT 'me2';
ALTER TABLE product_listings ADD free_shipping        NUMBER(1,0)  DEFAULT 0;
ALTER TABLE product_listings ADD video_id             VARCHAR2(100);

COMMIT;
