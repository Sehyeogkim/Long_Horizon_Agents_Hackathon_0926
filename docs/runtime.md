# 토마토 관측 MVP 실행

실행 코드는 `tomato_agent/`, 실제 입력은 `data/samples/tomato_18day/observations.jsonl`이다. 매 관측 Liquid를 실행한 뒤 저비용으로 종료하거나 GPT-5를 추가한다. 모델 학습은 하지 않는다.

## 준비

- Python 3.9 이상, `python3 -m pip install -r requirements.txt`.
- `liquid/setup.py`로 설치한 고정 버전 llama.cpp·Liquid 가중치. 이미 이 작업에서 설치·검증한 파일은 재사용한다.
- `.env`: `OPENAI_API_KEY` 또는 기존 `OPEN_AI_API_KEY`, `RAWTREE_API_KEY`, 데이터 검색 시 `NIMBLE_API_KEY`.
- RawTree MCP는 공식 `@rawtree/mcp@0.3.2`와 npx를 사용한다. 키는 자식 환경에만 전달한다.

## 실행 명령

```sh
# 데이터가 없는 새 환경: 검증된 원본 수집/일차·환경값 매칭
python3 scripts/collect_tomatoes.py

# 네트워크·모델 호출 없이 정책/저장/예산/재시작 검증
python3 -m unittest discover -s tests -p 'test_*.py'

# C: 실제 RawTree 기억을 사용하는 두 관측 연결 검사
python3 -m tomato_agent run --variant C --backend rawtree --run-id my_tomato_c --limit 2
# 같은 run-id와 설정으로 계속 실행: 성공한 호출/관측은 재사용
python3 -m tomato_agent run --variant C --backend rawtree --run-id my_tomato_c

# A/B: 같은 시퀀스를 사용하는 비교 실험
python3 -m tomato_agent run --variant A --backend local --run-id my_tomato_a
python3 -m tomato_agent run --variant B --backend local --run-id my_tomato_b

# 실제 실행 기록에서 공유 가능한 단일 HTML 생성
python3 -m tomato_agent report data/runs/my_tomato_a data/runs/my_tomato_b data/runs/my_tomato_c --output reports/tomato_demo.html
python3 -m http.server 8765 --bind 127.0.0.1 --directory reports
```

뷰어 주소는 `http://127.0.0.1:8765/tomato_demo.html`이다. 정적 HTML에 축소 이미지와 관측·판단·기억을 포함하므로 모델 서버가 없어도 볼 수 있다. 공개 배포는 하지 않는다.

Liquid 실행 포트는 `127.0.0.1:18081`이다. 이미 다른 서버가 사용 중이면 종료시키지 않고 실패한다. B와 C를 같은 머신에서 동시에 실행하지 않는다. A는 Liquid를 사용하지 않으므로 별도로 병렬 실행할 수 있다. 소유한 모델 서버는 성공·오류 모두 종료한다.

## 예산과 재시작

- 기본 GPT 요청 상한은 run당 20회다. `--max-gpt-calls`로 변경한다. 실패한 호출도 횟수에 포함한다.
- `--max-api-cost-usd` 기본값은 $1이다. 기록된 공개 단가 추정액과 다음 요청의 $0.10 예약 여유로 실행을 제한한다. 이는 결제 시스템의 엄밀한 청구 한도가 아니다. 반환된 사용량이 없는 호출은 비용 미측정으로 남기고 다음 유료 요청을 중단한다.
- 유료 요청 전 intent를 디스크에 기록하고 응답은 별도 로그에 fsync한다. 응답 수신 후 원격 저장 전에 중단되면 로컬 모델 로그에서 복원한다. 요청을 보낸 뒤 응답을 저장하지 못해 결과가 불명확하면 자동 재호출하지 않는다.
- 새 run-id는 새 실험이므로 비용이 다시 발생한다. 이어서 실행할 때는 같은 run-id·manifest·정책·backend를 유지한다.
- 현재 MCP 저장은 단일 writer 기반이다. 동시에 같은 run-id를 실행하지 않는다. 서버의 원자적 중복 방지 기능을 가정하지 않는다.

## 기억·시간·평가 경계

- C는 RawTree `run-query`로 직전 시점의 기억을 복원하고 `insert-json`으로 관측·호출·결정·전체 기억 스냅샷을 저장한다. 네트워크 실패 시 로컬 outbox를 보존하고 성공으로 위장하지 않는다.
- A/B의 비교 실행은 로컬 이벤트 로그, C는 RawTree를 사용한다. 모델 호출·API 비용 비교는 가능하지만 DB 지연을 포함한 종단간 지연을 같은 조건의 비교로 주장하지 않는다.
- B에는 마지막 분석 시각 같은 운영 상태만 제공하고, 의미 있는 요약·과거 사진·미해결 질문은 제공하지 않는다.
- 매 관측 Liquid 성공 시각과 GPT-5 성공 시각을 분리한다. 흐린 사진은 재촬영 과제로 남기고 정상으로 처리하지 않는다.
- 초기 정책은 최대 정밀 분석 공백 72시간, 관측별 기한/새 이상/불확실성 규칙이다. 이미지 차이만으로 경로를 선택하지 않는다. 일차 기반 상대 시간은 정확한 촬영 타임스탬프가 아니다.
- 현재 모델 입력은 RGB와 C의 제한된 과거 근거다. 환경값은 기록·화면에서 제공하지만 아직 판단 규칙이나 모델 입력에 사용하지 않는다. 센서까지 사용하는 실험은 별도 버전으로 구분한다.
- 데이터는 단일 토마토 18장이고 병리 정답이 없다. recall·오탐률·질병 탐지 지연은 `null`이다. GPT-5 결과를 정답으로 간주하지 않는다.
- B/C는 동일한 Liquid·정책을 사용하며 C의 기억을 추가한다. 각 실행에서 Liquid를 따로 호출하므로 출력 변동이 섞일 수 있다. 기억만의 인과 효과를 분리하려면 동일한 저비용 출력 캐시를 공유하는 후속 ablation이 필요하다. GPT-5는 같은 모델·출력 계약을 사용하되 C에 필요한 과거 근거가 더해져 입력 토큰이 증가할 수 있다.

## 파일

- `data/runs/<run-id>/run.json`: 고정 설정과 manifest 해시.
- `store/events.jsonl`, `acknowledgements.jsonl`: 관측·호출·정책·기억과 원격 저장 확인.
- `paid_request_intents.jsonl`, `model_calls.jsonl`: 유료 호출 복구 기록, 비밀키·이미지 요청 본문 없음.
- `summary.json`: 성공·실패 호출, 사용량, 공개 단가 기반 비용 추정, 미측정 지표.
- `reports/tomato_demo.html`, `.json`: 대화형 관측 재생과 비교 결과.

BFL은 키 대기 중인 선택적 합성 시나리오 도구다. 실제 토마토·Liquid·RawTree·Nimble MVP 실행에 필요하지 않다.
