-- mysql_schema.sql
-- 为 What-2-Eat 系统生成的 MySQL 建表语句
-- ─────────────────────────────────────────────────────────────────────

-- 创建并使用数据库
CREATE DATABASE IF NOT EXISTS what2eat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE what2eat;

-- 1. 标签体系表
CREATE TABLE IF NOT EXISTS tag (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(50) NOT NULL UNIQUE,
    type        VARCHAR(20) NOT NULL COMMENT 'cuisine / taste / type / scene / feature',
    description TEXT,
    parent_id   BIGINT,
    FOREIGN KEY (parent_id) REFERENCES tag(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 用户表
CREATE TABLE IF NOT EXISTS user (
    id          VARCHAR(100) PRIMARY KEY,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 用户偏好表
CREATE TABLE IF NOT EXISTS user_tag_preference (
    user_id     VARCHAR(100) NOT NULL,
    tag_id      BIGINT NOT NULL,
    preference  FLOAT DEFAULT 0.5,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tag_id),
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tag(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 餐馆缓存表
CREATE TABLE IF NOT EXISTS restaurant (
    id          VARCHAR(100) PRIMARY KEY COMMENT '高德 POI ID',
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(100),
    address     VARCHAR(255),
    latitude    DOUBLE,
    longitude   DOUBLE,
    rating      FLOAT DEFAULT 0,
    avg_price   FLOAT DEFAULT 0,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_lat_lng (latitude, longitude)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 餐馆-标签关联表
CREATE TABLE IF NOT EXISTS restaurant_tag (
    restaurant_id VARCHAR(100) NOT NULL,
    tag_id        BIGINT NOT NULL,
    weight        FLOAT DEFAULT 1.0,
    PRIMARY KEY (restaurant_id, tag_id),
    FOREIGN KEY (restaurant_id) REFERENCES restaurant(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tag(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 查询记录表
CREATE TABLE IF NOT EXISTS user_query (
    id          VARCHAR(100) PRIMARY KEY COMMENT 'UUID',
    user_id     VARCHAR(100),
    longitude   DOUBLE,
    latitude    DOUBLE,
    radius      INT,
    budget_min  FLOAT,
    budget_max  FLOAT,
    taste       VARCHAR(100),
    query_text  TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE SET NULL,
    INDEX idx_user_time (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 推荐结果表
CREATE TABLE IF NOT EXISTS recommendation (
    id              VARCHAR(100) PRIMARY KEY COMMENT 'UUID',
    query_id        VARCHAR(100) REFERENCES user_query(id) ON DELETE CASCADE,
    restaurant_id   VARCHAR(100),
    restaurant_name VARCHAR(100),
    rank_index      INT COMMENT 'rank is a reserved word in MySQL 8.0',
    final_score     FLOAT,
    score_distance  FLOAT,
    score_price     FLOAT,
    score_rating    FLOAT,
    score_tag       FLOAT,
    matched_tags    JSON COMMENT 'MySQL supports JSON',
    reason_hint     JSON,
    explain_json    JSON,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_id (query_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 用户反馈表
CREATE TABLE IF NOT EXISTS feedback (
    id                VARCHAR(100) PRIMARY KEY COMMENT 'UUID',
    user_id           VARCHAR(100),
    recommendation_id VARCHAR(100),
    restaurant_id     VARCHAR(100),
    rating            INT,
    chosen            TINYINT(1) DEFAULT 0,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (recommendation_id) REFERENCES recommendation(id) ON DELETE SET NULL,
    INDEX idx_user_res (user_id, restaurant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 行为交互表
CREATE TABLE IF NOT EXISTS interaction (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       VARCHAR(100) NOT NULL,
    restaurant_id VARCHAR(100) NOT NULL,
    action_type   VARCHAR(20) COMMENT 'click / LIKE / DISLIKE',
    score         FLOAT,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    INDEX idx_user_action (user_id, action_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
