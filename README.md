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
│   └── test_chatbot_learn.py  # 150개 질문 + LLM 품질 평가
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

# 리포트 생성
python generate_report.py
```

## 기술 스택

- **Python 3.11+** · **Playwright** · **pytest**
- **Ollama (qwen2.5:3b)** — 로컬 LLM 평가자
