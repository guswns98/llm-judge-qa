"""
evaluation_results/*.json 파일을 읽어 HTML 리포트를 생성하는 스크립트.

사용법:
    python generate_report.py
"""

import json
from pathlib import Path

EVAL_DIR = Path("evaluation_results")
HISTORY_DIR = EVAL_DIR / "history"
REPORT_PATH = EVAL_DIR / "report.html"


def load_results() -> list[dict]:
    """개별 평가 JSON 파일들을 로드"""
    results = []
    for filepath in sorted(EVAL_DIR.glob("eval_*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            results.append(json.load(f))
    return results


def load_summary() -> dict | None:
    """evaluation_summary.json 로드"""
    summary_path = EVAL_DIR / "evaluation_summary.json"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_history() -> list[dict]:
    """이력 파일들을 시간순으로 로드 (최근 10개)"""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("summary_*.json"))
    history = []
    for f in files[-10:]:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            history.append({
                "run_id": data.get("run_id", f.stem),
                "average_score": data.get("average_score", 0),
                "evaluated": data.get("evaluated", 0),
                "eval_runs_per_question": data.get("eval_runs_per_question", 1),
                "score_distribution": data.get("score_distribution", {}),
            })
    return history


def _axis_regression_html(regression: dict) -> str:
    """축별 회귀 감지 HTML 생성"""
    axis_reg = regression.get("axis_regression", {})
    if not axis_reg:
        return ""
    labels = {"relevance": "관련성", "accuracy": "정확성", "completeness": "완결성"}
    rows = ""
    for axis in ["relevance", "accuracy", "completeness"]:
        ar = axis_reg.get(axis, {})
        if not ar:
            continue
        d = ar.get("diff", 0)
        color = "#ef4444" if d < 0 else "#22c55e" if d > 0 else "#9ca3af"
        arrow = "&#9660;" if d < 0 else "&#9650;" if d > 0 else "&#9472;"
        badge = ""
        if ar.get("is_regression"):
            badge = ' <span style="background:#ef4444; color:white; padding:1px 8px; border-radius:8px; font-size:0.75em;">REGRESSION</span>'
        rows += f"""
            <tr>
                <td style="font-weight:600;">{labels[axis]}</td>
                <td style="text-align:center">{ar.get('previous_avg', 0):.2f}</td>
                <td style="text-align:center; color:{color};">{arrow} {abs(d):.2f}</td>
                <td style="text-align:center">{ar.get('current_avg', 0):.2f}</td>
                <td>{badge}</td>
            </tr>"""
    return f"""
            <div style="margin-top:8px;">
                <h3 style="font-size:0.95em; margin-bottom:8px;">축별 회귀 분석</h3>
                <table style="width:auto;">
                    <thead><tr>
                        <th>축</th><th>이전</th><th>변동</th><th>현재</th><th></th>
                    </tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>"""


def generate_html(results: list[dict]) -> str:
    """평가 결과를 HTML 리포트로 변환 (Multi-run + Regression 포함)"""
    summary = load_summary()
    history = load_history()

    valid_scores = [r["score"] for r in results if r["score"] > 0]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    total = len(results)
    distribution = {s: len([r for r in results if r["score"] == s]) for s in range(1, 6)}

    eval_runs = summary.get("eval_runs_per_question", 1) if summary else 1
    regression = summary.get("regression") if summary else None
    avg_relevance = summary.get("average_relevance", 0) if summary else 0
    avg_accuracy = summary.get("average_accuracy", 0) if summary else 0
    avg_completeness = summary.get("average_completeness", 0) if summary else 0
    weights = summary.get("weights", {}) if summary else {}

    def score_color(score):
        colors = {5: "#22c55e", 4: "#84cc16", 3: "#eab308", 2: "#f97316", 1: "#ef4444", 0: "#9ca3af"}
        return colors.get(score, "#9ca3af")

    max_count = max(distribution.values()) if distribution.values() else 1

    rows = ""
    for r in results:
        color = score_color(r["score"])
        run_scores = r.get("run_scores", [])
        run_info = f' title="runs: {run_scores}"' if run_scores else ""
        rel = r.get("relevance", 0)
        acc = r.get("accuracy", 0)
        comp = r.get("completeness", 0)
        rows += f"""
        <tr>
            <td style="text-align:center">{r['index']}</td>
            <td>{r['question']}</td>
            <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
                title="{r['response'][:200].replace('"', '&quot;')}">{r['response'][:80]}</td>
            <td style="text-align:center"{run_info}>
                <span style="background:{color}; color:white; padding:2px 10px; border-radius:12px; font-weight:bold;">
                    {r['score']}
                </span>
            </td>
            <td style="text-align:center"><span style="background:{score_color(rel)}; color:white; padding:2px 8px; border-radius:12px;">{rel}</span></td>
            <td style="text-align:center"><span style="background:{score_color(acc)}; color:white; padding:2px 8px; border-radius:12px;">{acc}</span></td>
            <td style="text-align:center"><span style="background:{score_color(comp)}; color:white; padding:2px 8px; border-radius:12px;">{comp}</span></td>
            <td style="font-size:0.85em; color:#555;">{r['evaluation'][:150]}</td>
        </tr>"""

    dist_bars = ""
    for score in range(5, 0, -1):
        count = distribution.get(score, 0)
        pct = (count / total * 100) if total > 0 else 0
        bar_width = (count / max_count * 100) if max_count > 0 else 0
        dist_bars += f"""
        <div style="display:flex; align-items:center; margin:4px 0;">
            <span style="width:30px; font-weight:bold; color:{score_color(score)}">{score}점</span>
            <div style="flex:1; background:#f3f4f6; border-radius:4px; margin:0 8px; height:20px;">
                <div style="width:{bar_width}%; background:{score_color(score)}; height:100%; border-radius:4px;
                     display:flex; align-items:center; justify-content:flex-end; padding-right:6px;
                     color:white; font-size:0.75em; font-weight:bold; min-width:fit-content;">
                    {count}
                </div>
            </div>
            <span style="width:50px; font-size:0.85em; color:#888;">{pct:.1f}%</span>
        </div>"""

    # Regression Detection 섹션
    regression_html = ""
    if regression:
        diff = regression["diff"]
        arrow = "&#9660;" if diff < 0 else "&#9650;" if diff > 0 else "&#9472;"
        diff_color = "#ef4444" if diff < 0 else "#22c55e" if diff > 0 else "#9ca3af"
        status = "REGRESSION" if regression["is_regression"] else "OK"
        status_color = "#ef4444" if regression["is_regression"] else "#22c55e"

        regressed_rows = ""
        for rq in regression.get("regressed_questions", []):
            regressed_rows += f"""
            <tr>
                <td style="text-align:center">#{rq['index']}</td>
                <td style="text-align:center">{rq['previous_score']}</td>
                <td style="text-align:center">{rq['current_score']}</td>
                <td style="text-align:center; color:#ef4444; font-weight:bold;">{rq['drop']:+d}</td>
            </tr>"""

        regressed_table = ""
        if regressed_rows:
            regressed_table = f"""
            <div style="margin-top:12px;">
                <h3 style="font-size:0.95em; margin-bottom:8px;">급락 질문 (2점 이상 하락)</h3>
                <table style="width:auto;">
                    <thead><tr>
                        <th>질문 #</th><th>이전 점수</th><th>현재 점수</th><th>변동</th>
                    </tr></thead>
                    <tbody>{regressed_rows}</tbody>
                </table>
            </div>"""

        regression_html = f"""
        <div class="section">
            <h2 style="margin-bottom:12px;">Score Regression Detection</h2>
            <div style="display:flex; gap:24px; align-items:center; margin-bottom:12px;">
                <div>
                    <span style="color:#64748b; font-size:0.85em;">이전 평균</span>
                    <div style="font-size:1.4em; font-weight:700;">{regression['previous_avg']:.2f}</div>
                </div>
                <div style="font-size:1.5em; color:{diff_color};">{arrow} {abs(diff):.2f}</div>
                <div>
                    <span style="color:#64748b; font-size:0.85em;">현재 평균</span>
                    <div style="font-size:1.4em; font-weight:700;">{regression['current_avg']:.2f}</div>
                </div>
                <div style="margin-left:auto;">
                    <span style="background:{status_color}; color:white; padding:4px 16px;
                           border-radius:12px; font-weight:bold; font-size:0.9em;">{status}</span>
                </div>
            </div>
            <p style="font-size:0.85em; color:#64748b; margin-bottom:12px;">
                임계값: {regression['threshold']} | 이전 실행: {regression['previous_run']}
            </p>
            {_axis_regression_html(regression)}
            {regressed_table}
        </div>"""

    # 점수 추이 차트 (이력 기반)
    trend_html = ""
    if len(history) >= 2:
        trend_points = ""
        max_runs = len(history)
        chart_width = 500
        chart_height = 150
        x_step = chart_width / max(max_runs - 1, 1)

        for i, h in enumerate(history):
            x = i * x_step
            y = chart_height - (h["average_score"] / 5.0 * chart_height)
            trend_points += f"{x},{y} "

        point_dots = ""
        point_labels = ""
        for i, h in enumerate(history):
            x = i * x_step
            y = chart_height - (h["average_score"] / 5.0 * chart_height)
            point_dots += f'<circle cx="{x}" cy="{y}" r="4" fill="#3b82f6"/>'
            label = h["run_id"][-6:] if len(h["run_id"]) > 6 else h["run_id"]
            point_labels += f'<text x="{x}" y="{chart_height + 16}" text-anchor="middle" font-size="9" fill="#94a3b8">{label}</text>'
            point_labels += f'<text x="{x}" y="{y - 8}" text-anchor="middle" font-size="10" fill="#1e293b" font-weight="bold">{h["average_score"]:.2f}</text>'

        trend_html = f"""
        <div class="section">
            <h2 style="margin-bottom:12px;">점수 추이 (최근 {len(history)}회)</h2>
            <svg viewBox="-20 -25 {chart_width + 40} {chart_height + 40}" style="width:100%; max-width:600px;">
                <line x1="0" y1="0" x2="0" y2="{chart_height}" stroke="#e2e8f0" stroke-width="1"/>
                <line x1="0" y1="{chart_height}" x2="{chart_width}" y2="{chart_height}" stroke="#e2e8f0" stroke-width="1"/>
                <line x1="0" y1="{chart_height * 0.6}" x2="{chart_width}" y2="{chart_height * 0.6}" stroke="#fecaca" stroke-width="1" stroke-dasharray="4"/>
                <text x="-5" y="{chart_height * 0.6 + 4}" text-anchor="end" font-size="9" fill="#ef4444">2.0</text>
                <polyline points="{trend_points.strip()}" fill="none" stroke="#3b82f6" stroke-width="2"/>
                {point_dots}
                {point_labels}
            </svg>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quantus 챗봇 응답 품질 리포트</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f8fafc; color: #1e293b; padding: 24px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.8em; margin-bottom: 8px; }}
        .subtitle {{ color: #64748b; margin-bottom: 24px; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                  gap: 16px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card-label {{ font-size: 0.85em; color: #64748b; margin-bottom: 4px; }}
        .card-value {{ font-size: 1.8em; font-weight: 700; }}
        .section {{ background: white; border-radius: 12px; padding: 20px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f1f5f9; padding: 10px 12px; text-align: left;
              font-size: 0.85em; color: #475569; border-bottom: 2px solid #e2e8f0; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 0.9em; }}
        tr:hover {{ background: #f8fafc; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Quantus 챗봇 응답 품질 리포트</h1>
        <p class="subtitle">LLM-as-a-Judge 3축 독립 평가 (Ollama {OLLAMA_MODEL}) | 관련성·정확성·완결성 가중평균 | 질문당 {eval_runs}회 반복 Median</p>

        <div class="cards">
            <div class="card">
                <div class="card-label">총 질문 수</div>
                <div class="card-value">{total}</div>
            </div>
            <div class="card">
                <div class="card-label">종합 점수 (가중평균)</div>
                <div class="card-value" style="color:{score_color(round(avg_score))}">{avg_score:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">관련성 평균{' (×' + str(weights.get('relevance', 1.0)) + ')' if weights else ''}</div>
                <div class="card-value" style="color:{score_color(round(avg_relevance))}">{avg_relevance:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">정확성 평균{' (×' + str(weights.get('accuracy', 1.5)) + ')' if weights else ''}</div>
                <div class="card-value" style="color:{score_color(round(avg_accuracy))}">{avg_accuracy:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">완결성 평균{' (×' + str(weights.get('completeness', 1.0)) + ')' if weights else ''}</div>
                <div class="card-value" style="color:{score_color(round(avg_completeness))}">{avg_completeness:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">4점 이상 비율</div>
                <div class="card-value">{((distribution.get(4, 0) + distribution.get(5, 0)) / total * 100) if total else 0:.1f}%</div>
            </div>
        </div>

        {regression_html}

        {trend_html}

        <div class="section">
            <h2 style="margin-bottom:12px;">점수 분포</h2>
            {dist_bars}
        </div>

        <div class="section">
            <h2 style="margin-bottom:12px;">상세 평가 결과</h2>
            <p style="font-size:0.85em; color:#64748b; margin-bottom:8px;">
                관련성·정확성·완결성 3축 독립 채점 후 가중 평균으로 종합 점수 산출 (median 기반)
            </p>
            <div style="overflow-x:auto;">
                <table>
                    <thead>
                        <tr>
                            <th style="width:40px">#</th>
                            <th style="width:160px">질문</th>
                            <th style="width:240px">챗봇 응답</th>
                            <th style="width:60px">종합</th>
                            <th style="width:60px">관련성</th>
                            <th style="width:60px">정확성</th>
                            <th style="width:60px">완결성</th>
                            <th>평가 근거</th>
                        </tr>
                    </thead>
                    <tbody>{rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>"""
    return html


def main():
    results = load_results()
    if not results:
        print("[ERROR] evaluation_results/ 디렉토리에 eval_*.json 파일이 없습니다.")
        print("        먼저 pytest tests/test_chatbot_learn.py를 실행하세요.")
        return

    html = generate_html(results)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"[SUCCESS] 리포트 생성 완료: {REPORT_PATH}")
    print(f"          총 {len(results)}개 평가 결과 포함")


OLLAMA_MODEL = "qwen2.5:3b"  # 리포트 표시용

if __name__ == "__main__":
    main()
