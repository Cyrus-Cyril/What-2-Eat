"""快速诊断：直接调用 LLM 生成 ai_speech，打印 raw 结果"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config

async def main():
    print(f"LLM providers: {len(config.LLM_PROVIDERS)}")
    for i, p in enumerate(config.LLM_PROVIDERS):
        key_preview = (p["key"][:8] + "...") if p["key"] else "EMPTY"
        print(f"  [{i}] model={p['model']}  key={key_preview}")

    if not config.LLM_PROVIDERS:
        print("ERROR: No LLM providers configured!")
        return

    from app.services.explanation_builder import build_ai_speeches_for_top_n
    from app.models.schemas import DimensionDetail, ReasoningLogic

    # 构造 3 家餐厅的模拟输入（与实际流程一致）
    test_inputs = [
        {
            "name": "巴蜀印象火锅",
            "match_details": [
                DimensionDetail(dimension="距离", detail="步行300米，出门就到", score_impact="high"),
                DimensionDetail(dimension="口味", detail="正宗四川麻辣口味，牛油底料", score_impact="high"),
                DimensionDetail(dimension="价格", detail="人均65元，中等消费", score_impact="medium"),
            ],
            "reasoning_logic": ReasoningLogic(primary_factor="距离近", secondary_factor="口味匹配"),
        },
        {
            "name": "小龙坎老火锅",
            "match_details": [
                DimensionDetail(dimension="评分", detail="大众点评4.5分，近千条好评", score_impact="high"),
                DimensionDetail(dimension="距离", detail="步行800米，略远", score_impact="medium"),
                DimensionDetail(dimension="价格", detail="人均90元，偏贵", score_impact="low"),
            ],
            "reasoning_logic": ReasoningLogic(primary_factor="口碑好", secondary_factor="经典品牌"),
        },
        {
            "name": "渝味十足串串香",
            "match_details": [
                DimensionDetail(dimension="价格", detail="人均35元，超划算", score_impact="high"),
                DimensionDetail(dimension="口味", detail="麻辣鲜香，串串风格", score_impact="high"),
                DimensionDetail(dimension="评分", detail="4.1分，评价一般", score_impact="low"),
            ],
            "reasoning_logic": ReasoningLogic(primary_factor="性价比高", secondary_factor="口味"),
        },
    ]

    import time
    print(f"\n调用 build_ai_speeches_for_top_n (3家餐厅)...")
    t0 = time.perf_counter()
    speeches = await build_ai_speeches_for_top_n(test_inputs)
    ms = (time.perf_counter() - t0) * 1000
    print(f"  耗时: {ms:.0f}ms")
    for i, s in enumerate(speeches):
        print(f"  [{i+1}] {s}")

if __name__ == "__main__":
    asyncio.run(main())
