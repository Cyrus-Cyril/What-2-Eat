-- schema.sql
-- 包含 DROP + CREATE，可反复执行
-- ─────────────────────────────────────────────────────────────────────

-- 1. 标签表
DROP TABLE IF EXISTS tag;
CREATE TABLE IF NOT EXISTS tag (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL,           -- cuisine / taste / type / scene / feature
    description TEXT,
    parent_id   INTEGER REFERENCES tag(id)
);

-- 2. 餐厅缓存表
DROP TABLE IF EXISTS restaurant;
CREATE TABLE IF NOT EXISTS restaurant (
    id          TEXT PRIMARY KEY,        -- 高德 POI ID
    name        TEXT NOT NULL,
    category    TEXT,                    -- 高德原始分类，如"中餐厅;川菜"
    address     TEXT,
    latitude    REAL,
    longitude   REAL,
    rating      REAL DEFAULT 0,
    avg_price   REAL DEFAULT 0,
    updated_at  TEXT
);

-- 3. 餐厅-标签关联表
DROP TABLE IF EXISTS restaurant_tag;
CREATE TABLE IF NOT EXISTS restaurant_tag (
    restaurant_id TEXT NOT NULL,
    tag_id        INTEGER NOT NULL,
    weight        REAL DEFAULT 1.0,
    PRIMARY KEY (restaurant_id, tag_id)
);

-- 4. 用户表
DROP TABLE IF EXISTS user;
CREATE TABLE IF NOT EXISTS user (
    id          TEXT PRIMARY KEY,
    created_at  TEXT
);

-- 5. 用户长期偏好表
DROP TABLE IF EXISTS user_tag_preference;
CREATE TABLE IF NOT EXISTS user_tag_preference (
    user_id     TEXT NOT NULL,
    tag_id      INTEGER NOT NULL,
    preference  REAL DEFAULT 0.5,
    updated_at  TEXT,
    PRIMARY KEY (user_id, tag_id)
);

-- 6. 行为记录表
DROP TABLE IF EXISTS interaction;
CREATE TABLE IF NOT EXISTS interaction (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    restaurant_id TEXT NOT NULL,
    action_type   TEXT,                  -- click / order / feedback
    score         REAL,
    timestamp     TEXT
);

-- 7. 查询记录表
DROP TABLE IF EXISTS user_query;
CREATE TABLE IF NOT EXISTS user_query (
    id          TEXT PRIMARY KEY,        -- UUID
    user_id     TEXT,
    longitude   REAL,
    latitude    REAL,
    radius      INTEGER,
    budget_min  REAL,
    budget_max  REAL,
    taste       TEXT,
    query_text  TEXT,
    created_at  TEXT
);

-- 8. 推荐记录表
DROP TABLE IF EXISTS recommendation;
CREATE TABLE IF NOT EXISTS recommendation (
    id              TEXT PRIMARY KEY,    -- UUID
    query_id        TEXT REFERENCES user_query(id),
    restaurant_id   TEXT,
    restaurant_name TEXT,
    rank            INTEGER,
    final_score     REAL,
    score_distance  REAL,
    score_price     REAL,
    score_rating    REAL,
    score_tag       REAL,
    matched_tags    TEXT,               -- JSON数组字符串
    reason_hint     TEXT,               -- JSON数组字符串
    explain_json    TEXT,               -- 完整explain JSON
    created_at      TEXT
);

-- 9. 反馈表
DROP TABLE IF EXISTS feedback;
CREATE TABLE IF NOT EXISTS feedback (
    id                TEXT PRIMARY KEY, -- UUID
    user_id           TEXT,
    recommendation_id TEXT REFERENCES recommendation(id),
    restaurant_id     TEXT,
    rating            INTEGER,
    chosen            INTEGER DEFAULT 0,
    created_at        TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_user_query_user_id ON user_query(user_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_query_id ON recommendation(query_id);
CREATE INDEX IF NOT EXISTS idx_interaction_user_id ON interaction(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tag_pref_user ON user_tag_preference(user_id);
