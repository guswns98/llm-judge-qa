"""
챗봇 150개 질문 자동 전송 + Ollama(LLM-as-a-Judge) 품질 평가

실행 방법:
    pytest tests/test_chatbot_learn.py -s --headed

평가 기준 (Score Card):
    5점: 관련성·정확성·완결성 완벽, 구체적이고 유용한 정보 제공
    4점: 대부분 충족하나 설명이 다소 부족함
    3점: 관련성은 있으나 정확성 또는 완결성 중 하나가 미흡함
    2점: 관련은 있으나 답변이 불충분하거나 일부 오류가 있음
    1점: 질문과 무관하거나 에러 메시지만 반환함
"""

import os
import json
import time
import re
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import requests
from dotenv import load_dotenv
from pages.chatbot_page import ChatbotPage

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://example.quantus.co.kr")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

EVAL_DIR = Path("evaluation_results")
HISTORY_DIR = EVAL_DIR / "history"

# Multi-run Median Aggregation 설정
EVAL_RUNS = int(os.getenv("EVAL_RUNS", "3"))  # 질문당 평가 반복 횟수

# Score Regression Detection 설정
REGRESSION_THRESHOLD = float(os.getenv("REGRESSION_THRESHOLD", "0.3"))  # 평균 점수 하락 허용치

# 3축 평가 가중치
WEIGHT_RELEVANCE = float(os.getenv("WEIGHT_RELEVANCE", "1.0"))
WEIGHT_ACCURACY = float(os.getenv("WEIGHT_ACCURACY", "1.5"))
WEIGHT_COMPLETENESS = float(os.getenv("WEIGHT_COMPLETENESS", "1.0"))

AXES = ["relevance", "accuracy", "completeness"]

# === 150개 질문 리스트 ===
QUESTIONS = [
    # 기본 인사 및 서비스 안내 (1-10)
    "안녕하세요",
    "Quantus가 뭐야?",
    "이 서비스는 어떤 기능이 있어?",
    "사용법을 알려줘",
    "도움말",
    "고객센터 연결해줘",
    "요금제 알려줘",
    "무료로 쓸 수 있어?",
    "회원가입 어떻게 해?",
    "비밀번호 재설정 방법",
    # 주요 종목 질의 (11-30)
    "삼성전자 주가 알려줘",
    "SK하이닉스 현재가는?",
    "네이버 주가 전망",
    "카카오 실적 분석해줘",
    "LG에너지솔루션 재무제표",
    "현대차 배당금 정보",
    "셀트리온 목표주가",
    "POSCO홀딩스 매출 추이",
    "삼성바이오로직스 PER",
    "기아 영업이익률",
    "KB금융 배당수익률",
    "신한지주 ROE",
    "삼성SDI 부채비율",
    "LG화학 매출액",
    "현대모비스 시가총액",
    "삼성물산 주가 흐름",
    "한국전력 적자 이유",
    "포스코퓨처엠 성장성",
    "에코프로비엠 밸류에이션",
    "두산에너빌리티 수주 현황",
    # 재무 지표 질의 (31-50)
    "PER이 뭐야?",
    "PBR 설명해줘",
    "ROE가 높으면 좋은 거야?",
    "EPS 뜻이 뭐야?",
    "BPS 계산 방법",
    "배당수익률 높은 종목 추천",
    "영업이익률이 중요한 이유",
    "부채비율이 높으면 위험해?",
    "유동비율이 뭐야?",
    "자기자본이익률 설명",
    "매출총이익률 해석",
    "순이익률 의미",
    "자산회전율 알려줘",
    "이자보상비율 뜻",
    "EV/EBITDA 설명",
    "PSR이 뭐야?",
    "PCR 의미 알려줘",
    "DPS가 뭐야?",
    "FCF 설명해줘",
    "ROIC가 뭐야?",
    # 투자 전략 질의 (51-70)
    "가치투자란?",
    "성장주 투자 전략",
    "배당주 투자 장단점",
    "모멘텀 투자 뜻",
    "분산투자 방법",
    "적립식 투자 장점",
    "장기투자 vs 단기투자",
    "코스피 vs 코스닥 차이",
    "ETF 투자 방법",
    "인덱스 펀드란?",
    "공매도가 뭐야?",
    "마진콜 뜻",
    "손절매 기준 설정법",
    "물타기 전략 괜찮아?",
    "스윙 트레이딩이란?",
    "데이 트레이딩 위험성",
    "포트폴리오 리밸런싱",
    "달러 코스트 에버리징",
    "섹터 로테이션 전략",
    "퀀트 투자 설명",
    # 시장 분석 (71-90)
    "오늘 코스피 지수",
    "코스닥 시장 동향",
    "미국 증시 영향",
    "환율이 주가에 미치는 영향",
    "금리 인상이 주식시장에 미치는 영향",
    "인플레이션과 주식의 관계",
    "반도체 섹터 전망",
    "2차전지 관련주 분석",
    "AI 관련주 추천",
    "바이오 섹터 동향",
    "금융주 전망",
    "건설주 분석",
    "자동차 섹터 전망",
    "엔터주 분석",
    "방산주 동향",
    "조선주 전망",
    "통신주 배당 매력",
    "유틸리티주 안정성",
    "리츠 투자 방법",
    "원자재 시장 동향",
    # 기술적 분석 (91-110)
    "이동평균선이 뭐야?",
    "골든크로스 뜻",
    "데드크로스 의미",
    "RSI 지표 해석",
    "MACD 사용법",
    "볼린저밴드 설명",
    "거래량 분석 방법",
    "캔들차트 읽는 법",
    "지지선과 저항선",
    "추세선 그리는 방법",
    "피보나치 되돌림",
    "스토캐스틱 지표",
    "일목균형표 설명",
    "OBV 지표란?",
    "윌리엄스 %R 해석",
    "ADX 지표 사용법",
    "CCI 지표 뜻",
    "파라볼릭 SAR 설명",
    "엘리어트 파동이론",
    "다우 이론 설명",
    # 경제 기초 (111-130)
    "GDP가 뭐야?",
    "기준금리란?",
    "양적완화 설명",
    "테이퍼링이 뭐야?",
    "CPI 의미",
    "실업률과 주가 관계",
    "경기순환이란?",
    "스태그플레이션 뜻",
    "디플레이션 설명",
    "무역수지가 뭐야?",
    "경상수지 의미",
    "재정정책 vs 통화정책",
    "국채 금리 의미",
    "수익률 곡선 역전",
    "VIX 공포지수란?",
    "블랙스완 이벤트",
    "서킷브레이커 발동 조건",
    "사이드카 제도 설명",
    "공시 확인하는 방법",
    "IR 자료 찾는 법",
    # 심화 질문 (131-150)
    "삼성전자 5년간 매출 추이 분석해줘",
    "반도체 업종 PER 비교해줘",
    "배당성장주 TOP 5 알려줘",
    "저PBR 고ROE 종목 찾아줘",
    "코스피200 구성 종목 알려줘",
    "외국인 순매수 상위 종목",
    "기관 순매도 종목 분석",
    "52주 신고가 종목",
    "52주 신저가 종목",
    "거래대금 상위 종목",
    "시가총액 TOP 10",
    "적자 전환 종목 분석",
    "흑자 전환 종목 추천",
    "자사주 매입 공시 종목",
    "유상증자 예정 종목",
    "무상증자 이력 종목",
    "스팩 합병 예정 종목",
    "관리종목 리스트",
    "상장폐지 위험 종목",
    "IPO 예정 종목 알려줘",
]


def _single_evaluate(question: str, response: str) -> tuple[dict, str]:
    """단일 Ollama 평가 호출. (axis_scores, evaluation_text) 반환"""
    prompt = f"""당신은 금융 챗봇의 응답 품질을 평가하는 전문 평가자입니다.

아래 3가지 축에 대해 각각 독립적으로 1-5점을 평가하고, 근거를 한 줄로 설명하세요.

[관련성] 질문에 대한 응답의 관련 정도
- 5점: 질문의 의도를 정확히 파악하고 직접적으로 관련된 정보 제공
- 3점: 주제와 관련은 있으나 질문의 핵심을 벗어남
- 1점: 질문과 완전히 무관하거나 에러 메시지만 반환

[정확성] 제공된 정보의 사실적 정확성
- 5점: 모든 정보가 사실적으로 정확하며 오류 없음
- 3점: 대체로 맞지만 일부 부정확한 정보 포함
- 1점: 심각한 사실 오류 또는 근거 없는 정보(할루시네이션)

[완결성] 답변의 충분함과 구체성
- 5점: 필요한 정보를 빠짐없이 구체적으로 제공
- 3점: 기본적인 답변은 하지만 세부 내용이 부족
- 1점: 답변이 극히 불충분하거나 빈 응답

[질문]
{question}

[챗봇 응답]
{response}

아래 형식으로만 답변하세요:
관련성: (1-5)
정확성: (1-5)
완결성: (1-5)
근거: (한 줄 설명)"""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        result_text = resp.json().get("response", "")
        axis_scores = _parse_axis_scores(result_text)
        return axis_scores, result_text.strip()
    except Exception as e:
        return {"relevance": 0, "accuracy": 0, "completeness": 0}, f"평가 실패: {str(e)}"


def evaluate_with_ollama(question: str, response: str, index: int) -> dict:
    """Multi-run Median Aggregation: N회 반복 평가 후 축별 중앙값을 최종 점수로 채택"""
    run_axis_scores = []
    run_evaluations = []

    for run in range(EVAL_RUNS):
        axis_scores, evaluation = _single_evaluate(question, response)
        run_axis_scores.append(axis_scores)
        run_evaluations.append(evaluation)

    # 축별 중앙값 계산
    median_axes = {}
    for axis in AXES:
        valid = [s[axis] for s in run_axis_scores if s[axis] > 0]
        median_axes[axis] = int(statistics.median(valid)) if valid else 0

    composite = _compute_composite(median_axes)
    score_int = round(composite)

    # 대표 평가 근거 선택
    representative_eval = run_evaluations[0]
    for i, s in enumerate(run_axis_scores):
        if all(s[axis] == median_axes[axis] for axis in AXES):
            representative_eval = run_evaluations[i]
            break

    return {
        "index": index,
        "question": question,
        "response": response,
        "score": score_int,
        "composite_score": composite,
        "relevance": median_axes["relevance"],
        "accuracy": median_axes["accuracy"],
        "completeness": median_axes["completeness"],
        "run_axis_scores": run_axis_scores,
        "run_scores": [round(_compute_composite(s)) for s in run_axis_scores],
        "evaluation": representative_eval,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _parse_score(text: str) -> int:
    """평가 텍스트에서 점수 추출 (하위 호환용)"""
    match = re.search(r"점수\s*:\s*(\d)", text)
    if match:
        score = int(match.group(1))
        return min(max(score, 1), 5)
    match = re.search(r"[1-5]", text)
    return int(match.group()) if match else 0


def _parse_axis_scores(text: str) -> dict:
    """평가 텍스트에서 3축 점수 추출"""
    labels = {"relevance": "관련성", "accuracy": "정확성", "completeness": "완결성"}
    scores = {}
    for axis, label in labels.items():
        match = re.search(rf"{label}\s*:\s*(\d)", text)
        if match:
            scores[axis] = min(max(int(match.group(1)), 1), 5)
        else:
            scores[axis] = 0
    return scores


def _compute_composite(axis_scores: dict) -> float:
    """가중 평균 종합 점수 계산"""
    weights = {
        "relevance": WEIGHT_RELEVANCE,
        "accuracy": WEIGHT_ACCURACY,
        "completeness": WEIGHT_COMPLETENESS,
    }
    total_weight = sum(weights.values())
    weighted_sum = sum(axis_scores[axis] * weights[axis] for axis in weights)
    return round(weighted_sum / total_weight, 2)


def _load_previous_summary() -> dict | None:
    """이력 디렉토리에서 가장 최근 평가 요약을 로드"""
    if not HISTORY_DIR.exists():
        return None
    history_files = sorted(HISTORY_DIR.glob("summary_*.json"))
    if not history_files:
        return None
    with open(history_files[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def _detect_regression(current_summary: dict, previous_summary: dict) -> dict:
    """이전 평가 이력과 비교하여 종합 + 축별 점수 회귀를 감지"""
    curr_avg = current_summary["average_score"]
    prev_avg = previous_summary["average_score"]
    diff = round(curr_avg - prev_avg, 2)

    # 카테고리별 회귀 분석 (질문 인덱스 기준)
    curr_by_idx = {r["index"]: r["score"] for r in current_summary["results"]}
    prev_by_idx = {r["index"]: r["score"] for r in previous_summary["results"]}

    regressed_questions = []
    for idx in sorted(set(curr_by_idx) & set(prev_by_idx)):
        score_diff = curr_by_idx[idx] - prev_by_idx[idx]
        if score_diff <= -2:
            regressed_questions.append({
                "index": idx,
                "previous_score": prev_by_idx[idx],
                "current_score": curr_by_idx[idx],
                "drop": score_diff,
            })

    # 축별 회귀 감지
    axis_regression = {}
    for axis in AXES:
        curr_axis_avg = current_summary.get(f"average_{axis}", 0)
        prev_axis_avg = previous_summary.get(f"average_{axis}", 0)
        axis_diff = round(curr_axis_avg - prev_axis_avg, 2)
        axis_regression[axis] = {
            "previous_avg": prev_axis_avg,
            "current_avg": curr_axis_avg,
            "diff": axis_diff,
            "is_regression": axis_diff < -REGRESSION_THRESHOLD,
        }

    is_regression = diff < -REGRESSION_THRESHOLD
    axis_regressions_detected = [
        axis for axis, r in axis_regression.items() if r["is_regression"]
    ]

    return {
        "previous_avg": prev_avg,
        "current_avg": curr_avg,
        "diff": diff,
        "is_regression": is_regression,
        "threshold": REGRESSION_THRESHOLD,
        "previous_run": previous_summary.get("run_id", "unknown"),
        "regressed_questions": regressed_questions,
        "axis_regression": axis_regression,
        "axis_regressions_detected": axis_regressions_detected,
    }


class TestChatbotEvaluation:
    """챗봇 150개 질문 자동 평가 테스트"""

    def test_chatbot_quality_evaluation(self, auth_page):
        """150개 질문을 전송하고 Ollama로 응답 품질을 평가 (Multi-run Median + Regression Detection)"""
        EVAL_DIR.mkdir(exist_ok=True)
        HISTORY_DIR.mkdir(exist_ok=True)
        chatbot = ChatbotPage(auth_page, BASE_URL)
        chatbot.navigate("/")
        chatbot.open_chatbot()

        run_id = time.strftime("%Y%m%d_%H%M%S")

        results = []
        eval_futures = []
        executor = ThreadPoolExecutor(max_workers=2)

        try:
            for i, question in enumerate(QUESTIONS, start=1):
                print(f"\n[{i}/{len(QUESTIONS)}] 질문: {question}")

                # 질문 전송 및 응답 대기
                response = chatbot.ask_and_get_response(question, timeout=60000)
                print(f"  응답 길이: {len(response)}자")

                # 응답 저장
                chatbot.save_result(i, question, response)

                # Ollama 평가 (백그라운드 스레드, N회 반복 후 중앙값)
                future = executor.submit(evaluate_with_ollama, question, response, i)
                eval_futures.append(future)

            # 모든 평가 완료 대기
            print(f"\n[INFO] Ollama 평가 결과 수집 중... (질문당 {EVAL_RUNS}회 반복, median 집계)")
            for future in as_completed(eval_futures):
                eval_result = future.result()
                results.append(eval_result)
                score = eval_result["score"]
                idx = eval_result["index"]
                run_scores = eval_result.get("run_scores", [])
                r_s = eval_result.get("relevance", 0)
                a_s = eval_result.get("accuracy", 0)
                c_s = eval_result.get("completeness", 0)
                print(f"  평가 완료 #{idx}: 종합 {score}점 (관련:{r_s} 정확:{a_s} 완결:{c_s} | runs: {run_scores})")

                # 개별 평가 결과 저장
                eval_path = EVAL_DIR / f"eval_{idx:03d}.json"
                eval_path.write_text(
                    json.dumps(eval_result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        finally:
            executor.shutdown(wait=True)

        # 결과 요약
        results.sort(key=lambda x: x["index"])
        valid_results = [r for r in results if r["score"] > 0]
        valid_scores = [r["score"] for r in valid_results]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0

        # 축별 평균
        axis_avgs = {}
        for axis in AXES:
            vals = [r[axis] for r in valid_results if r.get(axis, 0) > 0]
            axis_avgs[axis] = round(sum(vals) / len(vals), 2) if vals else 0

        summary = {
            "run_id": run_id,
            "eval_runs_per_question": EVAL_RUNS,
            "aggregation_method": "median",
            "total_questions": len(QUESTIONS),
            "evaluated": len(valid_scores),
            "average_score": round(avg_score, 2),
            "average_relevance": axis_avgs["relevance"],
            "average_accuracy": axis_avgs["accuracy"],
            "average_completeness": axis_avgs["completeness"],
            "weights": {
                "relevance": WEIGHT_RELEVANCE,
                "accuracy": WEIGHT_ACCURACY,
                "completeness": WEIGHT_COMPLETENESS,
            },
            "score_distribution": {
                str(s): len([r for r in results if r["score"] == s])
                for s in range(1, 6)
            },
            "results": results,
        }

        # === Score Regression Detection ===
        previous = _load_previous_summary()
        regression_result = None
        if previous:
            regression_result = _detect_regression(summary, previous)
            summary["regression"] = regression_result

        # 통합 결과 저장 (latest)
        summary_path = EVAL_DIR / "evaluation_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 이력 저장 (타임스탬프별)
        history_path = HISTORY_DIR / f"summary_{run_id}.json"
        history_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 결과 출력
        print(f"\n{'='*60}")
        print(f"평가 완료: {len(valid_scores)}/{len(QUESTIONS)}개")
        print(f"종합 점수: {avg_score:.2f}/5.00 (질문당 {EVAL_RUNS}회 median)")
        print(f"축별 평균: 관련성 {axis_avgs['relevance']:.2f} | 정확성 {axis_avgs['accuracy']:.2f} | 완결성 {axis_avgs['completeness']:.2f}")
        print(f"가중치: 관련성 {WEIGHT_RELEVANCE} | 정확성 {WEIGHT_ACCURACY} | 완결성 {WEIGHT_COMPLETENESS}")
        print(f"점수 분포: {summary['score_distribution']}")
        print(f"결과 저장: {summary_path}")
        print(f"이력 저장: {history_path}")

        if regression_result:
            diff = regression_result["diff"]
            arrow = "▼" if diff < 0 else "▲" if diff > 0 else "─"
            print(f"\n[Regression Detection]")
            print(f"  이전 평균: {regression_result['previous_avg']:.2f}")
            print(f"  현재 평균: {regression_result['current_avg']:.2f}")
            print(f"  변동: {arrow} {abs(diff):.2f}")
            if regression_result["regressed_questions"]:
                print(f"  급락 질문({len(regression_result['regressed_questions'])}개):")
                for rq in regression_result["regressed_questions"]:
                    print(f"    #{rq['index']}: {rq['previous_score']}→{rq['current_score']} ({rq['drop']:+d})")
            if regression_result["is_regression"]:
                print(f"  ⚠ 종합 점수 회귀 감지! (하락폭 {abs(diff):.2f} > 임계값 {REGRESSION_THRESHOLD})")
            else:
                print(f"  ✓ 종합 회귀 없음 (임계값: {REGRESSION_THRESHOLD})")

            # 축별 회귀 출력
            axis_labels = {"relevance": "관련성", "accuracy": "정확성", "completeness": "완결성"}
            for axis, ar in regression_result.get("axis_regression", {}).items():
                a_diff = ar["diff"]
                a_arrow = "▼" if a_diff < 0 else "▲" if a_diff > 0 else "─"
                status = "⚠ 회귀!" if ar["is_regression"] else "✓"
                print(f"  [{axis_labels[axis]}] {ar['previous_avg']:.2f} → {ar['current_avg']:.2f} ({a_arrow}{abs(a_diff):.2f}) {status}")
        else:
            print("\n[Regression Detection] 이전 이력 없음 — 첫 번째 실행")

        print(f"{'='*60}")

        # 절대 기준 + 회귀 기준 모두 체크
        assert avg_score >= 2.0, f"평균 점수가 절대 기준(2.0) 미만입니다: {avg_score:.2f}"
        if regression_result and regression_result["is_regression"]:
            pytest.fail(
                f"종합 점수 회귀 감지: 평균 {regression_result['previous_avg']:.2f} → "
                f"{regression_result['current_avg']:.2f} "
                f"(하락폭 {abs(regression_result['diff']):.2f} > 임계값 {REGRESSION_THRESHOLD})"
            )
        if regression_result and regression_result.get("axis_regressions_detected"):
            axis_labels = {"relevance": "관련성", "accuracy": "정확성", "completeness": "완결성"}
            failed_axes = [axis_labels[a] for a in regression_result["axis_regressions_detected"]]
            pytest.fail(f"축별 회귀 감지: {', '.join(failed_axes)} (임계값 {REGRESSION_THRESHOLD})")
