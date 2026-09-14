"""
Golden Set 검증: LLM 평가자(Ollama)의 채점 신뢰도를 검증

사람이 정답을 확정한 질문-응답-기대점수 세트를 LLM 평가자에게 채점시켜,
기대 점수와 실제 점수의 일치율로 평가자 신뢰도를 측정한다.

실행 방법:
    pytest tests/test_golden_set.py -s

통과 기준:
    - 허용 오차: ±1점
    - 일치율: 80% 이상
"""

import json
import time
from pathlib import Path

import pytest

from tests.test_chatbot_learn import evaluate_with_ollama

EVAL_DIR = Path("evaluation_results")

# === Golden Set: 사람이 검증한 질문-응답-기대점수 ===
GOLDEN_SET = [
    # --- 5점: 완벽한 답변 ---
    {
        "question": "PER이 뭐야?",
        "response": "PER(Price to Earnings Ratio, 주가수익비율)은 주가를 주당순이익(EPS)으로 나눈 값입니다. "
                     "예를 들어 주가가 50,000원이고 EPS가 5,000원이면 PER은 10배입니다. "
                     "PER이 낮을수록 이익 대비 주가가 저평가되어 있다고 해석할 수 있으며, "
                     "동일 업종 내 비교에 활용됩니다.",
        "expected_score": 5,
        "reason": "정의, 계산법, 예시, 활용법까지 정확하고 완결적",
    },
    {
        "question": "골든크로스 뜻",
        "response": "골든크로스(Golden Cross)는 단기 이동평균선이 장기 이동평균선을 아래에서 위로 돌파하는 현상입니다. "
                     "일반적으로 20일선이 60일선을 상향 돌파할 때를 말하며, 상승 추세 전환 신호로 해석됩니다. "
                     "다만 단독 지표로 매매 판단하기보다 거래량 등 다른 지표와 함께 확인하는 것이 좋습니다.",
        "expected_score": 5,
        "reason": "정의, 구체적 조건, 해석, 주의사항까지 포함",
    },
    {
        "question": "분산투자 방법",
        "response": "분산투자는 여러 자산에 나누어 투자하여 리스크를 줄이는 전략입니다. "
                     "방법으로는 (1) 자산군 분산: 주식, 채권, 부동산 등 다른 자산군에 배분, "
                     "(2) 종목 분산: 한 종목에 집중하지 않고 10~20개 종목에 분산, "
                     "(3) 시간 분산: 적립식으로 매수 시점을 나누어 평균 매입단가를 낮추는 방법이 있습니다.",
        "expected_score": 5,
        "reason": "정의와 구체적 방법 3가지를 체계적으로 설명",
    },

    # --- 4점: 대부분 충족하나 설명이 다소 부족 ---
    {
        "question": "ROE가 높으면 좋은 거야?",
        "response": "네, ROE(자기자본이익률)가 높으면 자기자본 대비 이익을 많이 내고 있다는 뜻이므로 일반적으로 좋은 신호입니다.",
        "expected_score": 4,
        "reason": "핵심은 맞지만, 부채 레버리지로 ROE가 높아질 수 있다는 주의점 누락",
    },
    {
        "question": "ETF 투자 방법",
        "response": "ETF는 증권사 앱에서 주식처럼 매수할 수 있습니다. 코스피200 ETF, 나스닥100 ETF 등 다양한 상품이 있으며, "
                     "소액으로도 분산투자가 가능합니다.",
        "expected_score": 4,
        "reason": "기본 설명은 맞지만 수수료, 추적오차 등 투자 시 고려사항 부족",
    },

    # --- 3점: 관련성은 있으나 정확성 또는 완결성 중 하나가 미흡 ---
    {
        "question": "MACD 사용법",
        "response": "MACD는 주가의 추세를 파악하는 기술적 지표입니다. 매수/매도 신호를 확인할 수 있습니다.",
        "expected_score": 3,
        "reason": "관련은 있으나 MACD선/시그널선 교차, 히스토그램 등 핵심 사용법 설명 없음",
    },
    {
        "question": "금리 인상이 주식시장에 미치는 영향",
        "response": "금리가 오르면 주식시장에 부정적인 영향을 줄 수 있습니다.",
        "expected_score": 3,
        "reason": "방향은 맞지만, 왜 부정적인지(할인율, 채권 매력도 등) 구체적 설명 없음",
    },

    # --- 2점: 관련은 있으나 답변이 불충분하거나 일부 오류 ---
    {
        "question": "볼린저밴드 설명",
        "response": "볼린저밴드는 주가 차트에서 사용하는 선입니다.",
        "expected_score": 2,
        "reason": "관련은 있으나 상한선/중심선/하한선, 표준편차 기반 등 핵심 내용 전무",
    },
    {
        "question": "배당수익률 높은 종목 추천",
        "response": "배당수익률이 높은 종목으로는 한국전력이 있습니다. 배당수익률은 약 15%입니다.",
        "expected_score": 2,
        "reason": "한국전력은 적자로 배당이 불안정하며, 15% 수치는 부정확",
    },

    # --- 1점: 질문과 무관하거나 에러 ---
    {
        "question": "삼성전자 주가 알려줘",
        "response": "죄송합니다. 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "expected_score": 1,
        "reason": "에러 메시지만 반환",
    },
    {
        "question": "코스피 vs 코스닥 차이",
        "response": "오늘 날씨가 좋습니다. 산책하기 좋은 날이네요.",
        "expected_score": 1,
        "reason": "질문과 완전히 무관한 응답",
    },
    {
        "question": "EPS 뜻이 뭐야?",
        "response": "",
        "expected_score": 1,
        "reason": "빈 응답",
    },
]

TOLERANCE = 1       # 허용 오차 ±1점
PASS_RATE = 0.80    # 일치율 80% 이상이면 통과


class TestGoldenSet:
    """LLM 평가자 신뢰도 검증 (Golden Set)"""

    def test_evaluator_reliability(self):
        """Golden Set으로 LLM 평가자의 채점 신뢰도를 검증"""
        EVAL_DIR.mkdir(exist_ok=True)

        results = []
        matched = 0

        for i, item in enumerate(GOLDEN_SET, start=1):
            print(f"\n[Golden Set {i}/{len(GOLDEN_SET)}] 질문: {item['question']}")
            print(f"  기대 점수: {item['expected_score']}점 ({item['reason']})")

            eval_result = evaluate_with_ollama(
                item["question"], item["response"], index=i
            )
            actual_score = eval_result["score"]
            expected_score = item["expected_score"]
            diff = abs(actual_score - expected_score)
            is_match = diff <= TOLERANCE

            if is_match:
                matched += 1

            status = "✓ PASS" if is_match else "✗ FAIL"
            print(f"  LLM 점수: {actual_score}점 | 차이: {diff} | {status}")
            print(f"  LLM 근거: {eval_result['evaluation']}")

            results.append({
                "index": i,
                "question": item["question"],
                "response": item["response"][:100],
                "expected_score": expected_score,
                "actual_score": actual_score,
                "diff": diff,
                "is_match": is_match,
                "reason": item["reason"],
                "llm_evaluation": eval_result["evaluation"],
            })

        # 결과 요약
        total = len(GOLDEN_SET)
        match_rate = matched / total if total > 0 else 0

        summary = {
            "total": total,
            "matched": matched,
            "match_rate": round(match_rate, 4),
            "tolerance": TOLERANCE,
            "pass_threshold": PASS_RATE,
            "passed": match_rate >= PASS_RATE,
            "results": results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        summary_path = EVAL_DIR / "golden_set_result.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\n{'='*50}")
        print(f"Golden Set 검증 결과")
        print(f"일치율: {matched}/{total} ({match_rate:.1%})")
        print(f"허용 오차: ±{TOLERANCE}점")
        print(f"통과 기준: {PASS_RATE:.0%}")
        print(f"결과: {'PASS' if match_rate >= PASS_RATE else 'FAIL'}")
        print(f"저장: {summary_path}")
        print(f"{'='*50}")

        assert match_rate >= PASS_RATE, (
            f"평가자 신뢰도 미달: 일치율 {match_rate:.1%} < 기준 {PASS_RATE:.0%}"
        )
