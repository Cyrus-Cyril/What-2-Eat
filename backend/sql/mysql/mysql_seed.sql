-- mysql_seed.sql
-- 为 What-2-Eat 系统生成的 MySQL 基础测试/种子数据
-- ─────────────────────────────────────────────────────────────────────

USE what2eat;

-- 1. 插入基础标签
INSERT INTO tag (name, type) VALUES 
('中餐', 'cuisine'),
('川菜', 'cuisine'),
('粤菜', 'cuisine'),
('辣', 'taste'),
('清淡', 'taste'),
('快餐', 'type'),
('火锅', 'type'),
('适合聚餐', 'scene'),
('性价比高', 'feature');

-- 设置父级关系（川菜/粤菜属于中餐）
UPDATE tag SET parent_id = (SELECT id FROM (SELECT id FROM tag WHERE name='中餐') as t) WHERE name IN ('川菜', '粤菜');

-- 2. 插入测试用户
INSERT INTO user (id) VALUES ('user_001'), ('user_002');

-- 3. 插入用户偏好 (user_001 喜欢辣和火锅)
INSERT INTO user_tag_preference (user_id, tag_id, preference) VALUES 
('user_001', (SELECT id FROM tag WHERE name='辣'), 0.8),
('user_001', (SELECT id FROM tag WHERE name='火锅'), 0.9),
('user_002', (SELECT id FROM tag WHERE name='粤菜'), 0.85);

-- 4. 插入测试餐厅
INSERT INTO restaurant (id, name, category, address, latitude, longitude, rating, avg_price) VALUES 
('res_abc_001', '海底捞火锅', '中餐厅;火锅', '某某路123号', 31.2304, 121.4737, 4.8, 120.0),
('res_abc_002', '老乡鸡', '中餐厅;快餐', '某某路456号', 31.2320, 121.4750, 4.2, 35.0);

-- 5. 餐厅打标
INSERT INTO restaurant_tag (restaurant_id, tag_id, weight) VALUES 
('res_abc_001', (SELECT id FROM tag WHERE name='火锅'), 1.0),
('res_abc_001', (SELECT id FROM tag WHERE name='辣'), 0.7),
('res_abc_001', (SELECT id FROM tag WHERE name='适合聚餐'), 0.9),
('res_abc_002', (SELECT id FROM tag WHERE name='快餐'), 1.0),
('res_abc_002', (SELECT id FROM tag WHERE name='性价比高'), 0.8);

-- 6. 插入一条查询记录
INSERT INTO user_query (id, user_id, radius, budget_max, query_text) VALUES 
('q_uuid_101', 'user_001', 3000, 150.0, '想吃火锅');

-- 7. 插入一条推荐结果
INSERT INTO recommendation (id, query_id, restaurant_id, restaurant_name, rank_index, final_score, matched_tags, reason_hint, explain_json) VALUES 
('r_uuid_201', 'q_uuid_101', 'res_abc_001', '海底捞火锅', 1, 0.92, 
 '["火锅", "辣"]', 
 '["口味匹配", "高分推荐"]', 
 '{"hello_voice": "为您推荐海底捞，这是一家火锅店...", "match_details": []}');

-- 8. 插入用户反馈
INSERT INTO feedback (id, user_id, recommendation_id, restaurant_id, rating, chosen) VALUES 
('f_uuid_301', 'user_001', 'r_uuid_201', 'res_abc_001', 5, 1);
