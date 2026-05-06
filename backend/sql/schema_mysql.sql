-- schema_mysql.sql
-- MySQL 8.0+ 数据库结构
-- 包含 DROP + CREATE，可反复执行

-- ─────────────────────────────────────────────────────
-- 变量名变更说明
-- ─────────────────────────────────────────────────────
-- 原表名 user
-- 修改为 app_user
-- 原因：
-- user 是 MySQL 保留关键字，容易导致 SQL 异常

-- 原字段名 recommendation.rank
-- 修改为 recommendation.rank_index
-- 原因：
-- rank 在部分 SQL 环境中可能与窗口函数冲突

-- ─────────────────────────────────────────────────────
-- 设置字符集
-- ─────────────────────────────────────────────────────

SET NAMES utf8mb4;

-- ─────────────────────────────────────────────────────
-- 1. 标签表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS tag;

CREATE TABLE tag (
    id INT PRIMARY KEY AUTO_INCREMENT,

    name VARCHAR(100) NOT NULL UNIQUE,

    type VARCHAR(50) NOT NULL,

    description TEXT,

    parent_id INT,

    CONSTRAINT fk_parent_tag
        FOREIGN KEY (parent_id)
        REFERENCES tag(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 2. 餐厅缓存表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS restaurant;

CREATE TABLE restaurant (
    id VARCHAR(100) PRIMARY KEY,

    name VARCHAR(100) NOT NULL,

    category VARCHAR(255),

    address VARCHAR(255),

    latitude DOUBLE,

    longitude DOUBLE,

    rating FLOAT DEFAULT 0,

    avg_price FLOAT DEFAULT 0,

    updated_at DATETIME

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 3. 餐厅-标签关联表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS restaurant_tag;

CREATE TABLE restaurant_tag (
    restaurant_id VARCHAR(100) NOT NULL,

    tag_id INT NOT NULL,

    weight FLOAT DEFAULT 1.0,

    PRIMARY KEY (restaurant_id, tag_id),

    CONSTRAINT fk_restaurant_tag_restaurant
        FOREIGN KEY (restaurant_id)
        REFERENCES restaurant(id),

    CONSTRAINT fk_restaurant_tag_tag
        FOREIGN KEY (tag_id)
        REFERENCES tag(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 4. 用户表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS app_user;

CREATE TABLE app_user (
    id VARCHAR(100) PRIMARY KEY,

    created_at DATETIME

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 5. 用户长期偏好表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS user_tag_preference;

CREATE TABLE user_tag_preference (
    user_id VARCHAR(100) NOT NULL,

    tag_id INT NOT NULL,

    preference FLOAT DEFAULT 0.5,

    updated_at DATETIME,

    PRIMARY KEY (user_id, tag_id),

    CONSTRAINT fk_user_pref_user
        FOREIGN KEY (user_id)
        REFERENCES app_user(id),

    CONSTRAINT fk_user_pref_tag
        FOREIGN KEY (tag_id)
        REFERENCES tag(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 6. 行为记录表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS interaction;

CREATE TABLE interaction (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    user_id VARCHAR(100) NOT NULL,

    restaurant_id VARCHAR(100) NOT NULL,

    action_type VARCHAR(50),

    score FLOAT,

    timestamp DATETIME,

    CONSTRAINT fk_interaction_user
        FOREIGN KEY (user_id)
        REFERENCES app_user(id),

    CONSTRAINT fk_interaction_restaurant
        FOREIGN KEY (restaurant_id)
        REFERENCES restaurant(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 7. 查询记录表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS user_query;

CREATE TABLE user_query (
    id VARCHAR(100) PRIMARY KEY,

    user_id VARCHAR(100),

    longitude DOUBLE,

    latitude DOUBLE,

    radius INT,

    budget_min FLOAT,

    budget_max FLOAT,

    taste VARCHAR(100),

    query_text TEXT,

    created_at DATETIME,

    CONSTRAINT fk_query_user
        FOREIGN KEY (user_id)
        REFERENCES app_user(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 8. 推荐记录表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS recommendation;

CREATE TABLE recommendation (
    id VARCHAR(100) PRIMARY KEY,

    query_id VARCHAR(100),

    restaurant_id VARCHAR(100),

    restaurant_name VARCHAR(100),

    rank_index INT,

    final_score FLOAT,

    score_distance FLOAT,

    score_price FLOAT,

    score_rating FLOAT,

    score_tag FLOAT,

    matched_tags JSON,

    reason_hint JSON,

    explain_json JSON,

    created_at DATETIME,

    CONSTRAINT fk_recommendation_query
        FOREIGN KEY (query_id)
        REFERENCES user_query(id),

    CONSTRAINT fk_recommendation_restaurant
        FOREIGN KEY (restaurant_id)
        REFERENCES restaurant(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 9. 用户反馈表
-- ─────────────────────────────────────────────────────

DROP TABLE IF EXISTS feedback;

CREATE TABLE feedback (
    id VARCHAR(100) PRIMARY KEY,

    user_id VARCHAR(100),

    recommendation_id VARCHAR(100),

    restaurant_id VARCHAR(100),

    rating INT,

    chosen TINYINT DEFAULT 0,

    created_at DATETIME,

    CONSTRAINT fk_feedback_user
        FOREIGN KEY (user_id)
        REFERENCES app_user(id),

    CONSTRAINT fk_feedback_recommendation
        FOREIGN KEY (recommendation_id)
        REFERENCES recommendation(id),

    CONSTRAINT fk_feedback_restaurant
        FOREIGN KEY (restaurant_id)
        REFERENCES restaurant(id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────────────
-- 索引
-- ─────────────────────────────────────────────────────

CREATE INDEX idx_user_query_user_id
ON user_query(user_id);

CREATE INDEX idx_recommendation_query_id
ON recommendation(query_id);

CREATE INDEX idx_interaction_user_id
ON interaction(user_id);

CREATE INDEX idx_user_tag_pref_user
ON user_tag_preference(user_id);

CREATE INDEX idx_restaurant_rating
ON restaurant(rating);

CREATE INDEX idx_restaurant_price
ON restaurant(avg_price);

CREATE INDEX idx_restaurant_category
ON restaurant(category);
