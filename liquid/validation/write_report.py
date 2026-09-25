"""Render final evaluation evidence without editing the shared project plan."""
import argparse
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def pct(metric):
    return f"{metric['count']}/{metric['denominator']} ({100*metric['rate']:.1f}%)"

def ci(metric):
    low,high=metric['wilson_95_image_level']
    return f'{100*low:.1f}–{100*high:.1f}%'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('runs',nargs='+',type=Path)
    args=parser.parse_args()
    sections=[]
    table=['| 평가 출처 | 사진 수 | 이상 원본의 추가 검토 재현율 | 정상 원본의 추가 검토율 | 유효 출력 | 중앙값 / p95 |',
           '|---|---:|---:|---:|---:|---:|']
    all_pass=True
    for index,run in enumerate(args.runs):
        m=json.loads((run/'metrics.json').read_text())
        title='동일 출처의 새 사진' if index==0 else '다른 출처의 외부 사진'
        table.append(f"| {title} | {m['n']} | {pct(m['infected_source_referral_recall'])} | {pct(m['healthy_source_referral_rate'])} | {pct(m['valid_output'])} | {m['latency_seconds']['median']:.2f} / {m['latency_seconds']['p95_nearest_rank']:.2f}초 |")
        all_pass=all_pass and m['all_provisional_gates_passed']
        mx=m['conservative_referral_matrix']
        gate_text=', '.join(k+': '+('통과' if v else '미달') for k,v in m['gate_results'].items())
        perception=m['perception_matrix']
        memory=m['memory_checks']
        relative=run.relative_to(HERE).as_posix()
        sections.append(f'''### {title}

- 추가 검토 TP {mx['TP']}, 놓친 이상 원본 FN {mx['FN']}, 정상 원본 추가 검토 FP {mx['FP']}, 정상 원본 일상 관측 TN {mx['TN']}.
- 원본 이상 라벨의 추가 검토 재현율 95% Wilson 구간: **{ci(m['infected_source_referral_recall'])}**. 정상 원본 추가 검토율 구간: **{ci(m['healthy_source_referral_rate'])}**.
- 관측 출력: 정상 원본 {json.dumps(perception['healthy'],ensure_ascii=False)}, 이상 원본 {json.dumps(perception['infected'],ensure_ascii=False)}.
- 위 관측 표의 invalid는 전체 출력 계약 실패다. 다른 필드 누락과 분리한 `visible_anomaly` 필드 자체는 {json.dumps(m['visible_anomaly_field_matrix'],ensure_ascii=False)}이다.
- 실제 선택한 경로 수: `{json.dumps(m['actions'],ensure_ascii=False)}`. 정밀 분석은 경로 선택만 했으며 GPT-5를 실행한 것이 아니다.
- 미해결 기억 검사: 모델 단독 정밀 분석 선택 {memory['raw_due_strong']}/{memory['due_count']}, 외부 규칙 적용 {memory['guard_due_strong']}/{memory['due_count']}.
- 사전 고정 선별 기준: {gate_text}.
- 서버 샘플링 최대 RSS {m['runtime']['sampled_peak_rss_bytes']/1024**3:.2f} GiB. 전처리 {m['runtime']['preprocess_seconds']:.2f}초, 서버 준비 {m['runtime']['startup_seconds']:.2f}초는 위 요청 지연과 별도.
- [세부 지표]({relative}/metrics.json), [모든 원본 응답]({relative}/responses.jsonl), [불일치·출력 오류 사례]({relative}/error_examples.json), [실행 전 고정 프로토콜]({relative}/protocol.json).
''')
    verdict=('이번 제한된 데이터에서 사전 선별 기준을 모두 통과했다. 실제 운영 채택은 별도 시간순·과실 단위 검증이 필요하다.' if all_pass else
             '**현재 설정은 사전 선별 기준을 모두 통과하지 못했다. 저비용 관측 후보로 연구를 이어갈 수 있지만 검증된 자동 판정기로 채택할 단계는 아니다.**')
    text=f'''# Liquid 사과 성능 검증 결과

2026-09-25. {verdict}

현재 공유 프로젝트 계획의 토마토 설계와 분리된 **사과 검증**이다. 사과 결과를 토마토 성능으로 일반화하지 않는다.

## 실제 측정 결과

{chr(10).join(table)}

"추가 검토"는 보호 규칙이 선택한 `strong_analysis` 또는 `retake_photo`다. 두 행동을 모두 이상을 무심코 넘기지 않는 경로로 집계했지만, 재촬영 요청을 GPT-5 호출로 세지 않는다. 정상/이상은 원본 데이터셋의 분류이며 전문 진단으로 새로 확정한 정답이 아니다.

{chr(10).join(sections)}
## 데이터·절차

- 초기 실험 4장과 정확한 파일 해시가 겹치지 않는 200장(정상100/이상100)을 고정 seed20260925로 선택했다. 다른 원본 데이터셋에서도 40장(정상20/부패20)을 선택했다. 이미지 선택을 모델 출력에 따라 바꾸지 않았다.
- [주 manifest](manifest.json), [외부 manifest](external/manifest.json)에 선택·출처·라벨·SHA256·동결 시각을 기록했다. 외부 데이터의 `infected`는 원본 `RottenApple`을 평가 코드에 맞춰 매핑한 값이다. 병원체 감염 확진을 의미하지 않는다.
- 모델·양자화·프롬프트는 앞선 4장 실험과 동일하다. 최대 변512px, image-max-tokens256, temperature0, seed42, 출력 상한160, JSON 문법 제약, 직렬 요청, 캐시 비활성화. 이번 결과를 보고 프롬프트나 임계값을 수정하지 않았다.
- 실행 전 임시 선별 기준을 **이상 원본 추가 검토 재현율≥95%, 정상 원본 추가 검토율≤20%, 출력 유효율≥99%, p95≤5초**로 고정했다. 프로젝트 내부의 실험 기준이며 임상·산업 표준이 아니다.
- 워밍업과 별도 기억 검사를 기본 성능 분모에서 제외했다. 실패·잘못된 출력은 제거하지 않고 실패율과 전체 분모에 포함했다. 잘못된 출력은 보수적으로 추가 분석 경로에 들어간다.
- 시간은 전처리와 서버 시작을 제외한 직렬 HTTP 요청부터 응답까지이며 실제 전처리 시간도 별도 기록했다. [동시 실행 기록](concurrent_runtime_observation.json)에서 다른 llama-server도 관찰되어 단독 GPU 벤치마크로 해석하면 안 된다. RSS는 서버 프로세스 지표이며 전체 통합 메모리 사용량이 아니다.
- 모델 추론은 로컬에서 실행했고 추론 API 청구액은 $0다. 전력·기기 점유 비용과 GPT 계열 비교 실행은 측정하지 않았다.

## 해석과 한계

1. 질병 진단 정확도가 아니라 **원본 정상/감염·부패 라벨과 관측·분기 결과의 일치**를 측정했다. 정상으로 분류된 사과에도 경미한 반점이 있을 수 있어, 모든 FP를 모델의 시각 오류로 단정할 수 없다. 별도의 전문가 이상 영역 라벨이 필요하다.
   [정성 오류 점검](qualitative_audit.md)은 실제 반점이 있는 정상 원본, 근거가 약한 모델 설명, 필드 누락에 의한 의뢰를 구분했다. 편의 선택한 사례이며 전문가 재라벨링은 수행하지 않았다.
2. 두 출처 모두 정적 사진이다. 질병 라벨과 발생 시점이 갖춰진 동일 사과 시계열은 이번 조사에서 확보하지 못했으므로 **조기진단, 탐지 지연, 장기 기억의 성능 향상은 검증하지 않았다.** [출처 감사](source_audit.md).
3. 파일 해시 중복을 배제해도 동일 과실의 다른 각도·유사 배경은 남을 수 있다. [유사사진 감사](duplicate_audit.json)의 dHash 후보는 독립 개체 수를 확정하지 않는다. Wilson 구간은 이미지 독립 가정하의 참고값으로, 실제 과실 수가 적으면 과도하게 좁을 수 있다.
4. 각 클래스 절반으로 구성한 인위적 유병률에서의 호출 비율을 실제 농장 비용 절감으로 바꾸면 안 된다. GPT-5 호출 비용·성능과 long-horizon A/B/C 비교는 별도다.
5. 기억 검사는 정상 원본 5장에 두 가지 텍스트 상태를 넣은 지시 이행 검사다. 외부 규칙이 기한을 처리하는 것은 구현된 분기의 결과이며 모델 자체의 장기 기억 능력이 아니다.
6. 작은 모델의 `visible_anomaly=no`가 실제 이상을 놓칠 가능성은 보호 규칙만으로 제거되지 않는다. 사람 확인·기한 기반 재검토·품질 확인의 운영 정책은 별도로 검증해야 한다.

## 산출물과 재실행

프로젝트 루트에서 실행한다. `evaluate.py`는 각 실행에 새로운 결과 폴더를 만들고 종료 시 자신이 띄운 서버를 종료한다.

```bash
python3 liquid/validation/prepare_data.py
python3 liquid/validation/evaluate.py
python3 liquid/validation/evaluate.py --manifest liquid/validation/external/manifest.json
python3 liquid/validation/analyze.py liquid/validation/runs/<run_id>
python3 -m unittest discover -s liquid/validation -p 'test_*.py'
```

다음 단계는 관측 전용의 짧은 출력 계약을 개발 세트에서 개선하고, 별도로 남겨 둔 사진과 **목표 작물** 데이터에서 검증하는 것이다. 이번 240장은 향후 수정에 활용하면 개발 데이터가 되므로 다시 최종 독립 검증이라고 부르지 않는다.
'''
    (HERE/'PERFORMANCE_REPORT.md').write_text(text)
    print(HERE/'PERFORMANCE_REPORT.md')

if __name__=='__main__':main()
