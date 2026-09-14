# LLM Judge QA

챗봇 응답 품질을 **LLM-as-a-Judge** 방식으로 자동 평가하는 E2E 테스트 프로젝트입니다.  
Playwright로 챗봇에 150개 질문을 자동 전송하고, 로컬 LLM(Ollama)이 응답의 관련성·정확성·완결성을 채점합니다.

## 아키텍처

```
┌─────────────┐     Playwright      ┌──────────────┐
│  Test Runner │ ──────────────────▶ │  Web Chatbot │
│  (pytest)    │ ◀────────────────── │  (Target)    │
└──────┬───────┘    질문 전송/응답 수집   └──────────────┘
       │
       │ 응답 데이터
       ▼
┌──────────────┐     REST API       ┌──────────────┐
│  Evaluator   │ ──────────────────▶ │   Ollama     │
│  (Thread)    │ ◀────────────────── │  (Local LLM) │
└──────┬───────┘   1~5점 채점 결과    └──────────────┘
       │
       ▼
┌──────────────┐
│    Report    │  → evaluation_results/report.html
│  Generator   │  → eval_NN.json (개별 결과)
└──────────────┘
```

## 프로젝트 구조

```
├── pages/                  # Page Object Model
│   ├── base_page.py        # 공통 네비게이션
│   ├── login_page.py       # 로그인/로그아웃
│   └── chatbot_page.py     # 챗봇 응답 감지 및 저장
├── tests/
│   ├── test_login.py       # 로그인 테스트
│   ├── test_chatbot.py     # 챗봇 기본 테스트 (비로그인)
│   ├── test_chatbot_learn.py  # 150개 질문 + LLM 품질 평가
│   └── test_golden_set.py  # LLM 평가자 신뢰도 검증 (Golden Set)
├── conftest.py             # pytest fixtures (인증, 세션 관리)
├── save_auth.py            # 로그인 세션 저장 스크립트
├── generate_report.py      # HTML 리포트 생성
└── requirements.txt
```

## 평가 기준

| 점수 | 설명 |
|------|------|
| 5 | 관련성·정확성·완결성 완벽, 구체적이고 유용한 정보 제공 |
| 4 | 대부분 충족하나 설명이 다소 부족 |
| 3 | 관련성은 있으나 정확성 또는 완결성 미흡 |
| 2 | 관련은 있으나 불충분하거나 일부 오류 |
| 1 | 질문과 무관하거나 에러 메시지만 반환 |

## 평가 신뢰성

### Multi-run Median Aggregation
질문당 3회(설정 가능) 반복 평가 후 중앙값을 최종 점수로 채택하여 LLM 채점의 비결정성을 완화합니다.

### Score Regression Detection
이전 평가 이력과 현재 결과의 평균 점수를 비교하여 품질 회귀를 자동 감지합니다.  
임계값(기본 0.3) 이상 하락 시 테스트를 실패 처리하고, 2점 이상 급락한 개별 질문도 추적합니다.

### Golden Set 검증
사람이 점수를 확정한 12개 질문-응답 세트로 LLM 평가자 자체의 채점 신뢰도를 검증합니다.  
허용 오차 ±1점, 일치율 80% 이상이면 통과합니다.

## 실행 방법

```bash
# 설치
pip install -r requirements.txt
playwright install chromium

# 환경 변수 설정
cp .env.example .env   # .env에 실제 값 입력

# 로그인 세션 저장 (최초 1회)
python save_auth.py

# 테스트 실행
pytest tests/test_chatbot_learn.py -s --headed

# Golden Set 검증 (평가자 신뢰도)
pytest tests/test_golden_set.py -s

# 리포트 생성
python generate_report.py
```

## 기술 스택

- **Python 3.11+** · **Playwright** · **pytest**
- **Ollama (qwen2.5:3b)** — 로컬 LLM 평가자
