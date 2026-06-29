-- 石化设备供应商主数据 —— 供应商-工厂-品类映射表
-- PostgreSQL 版本（需 pgcrypto 提供 gen_random_uuid；PG13+ 内置）
CREATE TABLE supplier_plant_mapping (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plant                VARCHAR(64)  NOT NULL,   -- 交付工厂：上海浦东 / 广州南沙 / 福建漳州古雷 / 重庆
    category             VARCHAR(64)  NOT NULL,   -- 设备品类（9 类之一）
    supplier_name        VARCHAR(128) NOT NULL,   -- 供应商全称
    qualification        VARCHAR(64)  NOT NULL,   -- 资质：A1/A2 · API Q1/ISO 9001/CE · 特种设备制造许可证（A级）
    distance_km          INTEGER      NOT NULL,   -- 供应商至工厂大致距离
    lead_time_days       INTEGER      NOT NULL,   -- 交付周期（与距离正相关）
    price_level          NUMERIC(4,2) NOT NULL,   -- 价格系数（行业均价=1.00）
    is_local             BOOLEAN      NOT NULL,   -- 是否属地供应商
    special_notes        VARCHAR(64),             -- 属地化特征 + 工艺优势
    reference_price_desc TEXT,                     -- 价格说明（含框架协议来源与预估价）
    created_at           TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT uq_plant_cat_supplier UNIQUE (plant, category, supplier_name)
);
CREATE INDEX idx_spm_plant_cat ON supplier_plant_mapping (plant, category);

-- ─────────────────────────────────────────────────────────────────────
-- MySQL 8.0 备选：
-- CREATE TABLE supplier_plant_mapping (
--     id                   CHAR(36)     PRIMARY KEY DEFAULT (UUID()),
--     plant                VARCHAR(64)  NOT NULL,
--     category             VARCHAR(64)  NOT NULL,
--     supplier_name        VARCHAR(128) NOT NULL,
--     qualification        VARCHAR(64)  NOT NULL,
--     distance_km          INT          NOT NULL,
--     lead_time_days       INT          NOT NULL,
--     price_level          DECIMAL(4,2) NOT NULL,
--     is_local             TINYINT(1)   NOT NULL,
--     special_notes        VARCHAR(64),
--     reference_price_desc TEXT,
--     created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
--     UNIQUE KEY uq_plant_cat_supplier (plant, category, supplier_name)
-- );
