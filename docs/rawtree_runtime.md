# 토마토 에이전트 이벤트 저장과 복원

`tomato_agent/storage.py`는 로컬 JSONL 영속 저장과 공식 RawTree MCP 저장을 같은 `EventStore` 인터페이스로 제공한다. RawTree 모드도 로컬 저널을 반드시 유지한다. REST API로 우회하지 않으며 `scripts/rawtree_mcp_probe.py`의 공식 stdio MCP client를 재사용한다.

## 사용 계약

```python
from pathlib import Path
from tomato_agent.storage import EventStore

with EventStore(Path("data/runs/example/journal"), backend="local") as store:
    store.append("memory_events", {
        "event_id": "example:tomato-1:memory:1",
        "run_id": "example",
        "entity_id": "tomato-1",
        "dataset_id": "example-dataset",
        "sequence_id": "sequence-1",
        "elapsed_seconds": 10.0,
        "record_version": 1,
        "kind": "memory_events",
        "state": {"open_questions": []},
    })
    memory_event = store.latest_memory("example", "tomato-1", as_of_seconds=10.0)
    state = memory_event["state"] if memory_event else None
    events = store.existing_events("example", kind="memory_events")
    store.flush()
```

- `root`는 로컬 저널 디렉터리다. API key 설정 위치와 무관하다.
- `backend="rawtree"`이면 `RAWTREE_API_KEY`를 사용하는 공식 MCP wrapper가 연결한다. 키는 명령행에 넣지 않는다.
- 허용 kind: `observations`, `agent_events`, `memory_events`, `model_calls`, `evaluation_results`.
- 실제 테이블: `tomato_lha_{kind}`. 기존 사과 및 다른 프로젝트 테이블의 내용은 읽거나 수정하지 않는다.
- `latest_memory`는 `state`만이 아니라 **기억 이벤트 전체**를 반환한다. 결과가 없으면 `None`이다.
- `existing_events`는 지정 run의 이벤트만 읽어 `event_id` 중복을 제거하고 재생 시간·버전·ID 순으로 반환한다.

## 저널과 원격 쓰기 순서

1. 공통 필드와 JSON 직렬화를 검증한다. 동일 event ID의 다른 payload는 오류다.
2. `events.jsonl`에 append하고 flush/fsync한다.
3. RawTree 모드에서는 해당 프로젝트 테이블과 run/event ID를 조회한다. 이미 동일 payload가 있으면 재삽입하지 않는다.
4. 미존재 이벤트는 MCP `insert-json`으로 넣는다. 원격 행에는 조회용 공통 필드와 원본 이벤트 전체의 canonical `event_json`을 저장한다. 모델 관측을 정답으로 변환하지 않는다.
5. 같은 ID를 MCP `run-query`로 재조회한다. 쓰기 성공 직후 보이지 않으면 즉시·0.3·0.7·1.5·3초 간격으로 최대 5번 조회만 시도한다(총 추가 대기 5.5초, 네트워크 시간 별도). 같은 시도에서 insert를 다시 보내지 않는다. payload가 일치할 때만 `acknowledgements.jsonl`에 완료 기록을 남긴다. 서버의 텍스트 쓰기 응답만으로 성공을 판정하지 않는다.

동일 `EventStore`에서 존재가 확인된 토마토 전용 테이블은 캐시하여 반복 `list-tables`를 생략한다. 없는 테이블은 캐시하지 않아 나중에 생성된 테이블을 발견한다. payload 조회·쓰기 후 재조회는 계속 실제 MCP를 호출한다.

실패 시 `StorageError`를 발생시키고 로컬 미완료 이벤트를 남긴다. 오류 메시지에 원격 응답 본문이나 키를 출력하지 않는다. 연결 복구 후 같은 root로 재시작하여 `flush()`하면 미완료 이벤트를 순서대로 처리한다. 재전송 전에 같은 최대 5번의 조회 대기를 수행하여 아직 보이지 않던 기존 쓰기를 확인한다. 끝까지 없을 때만 재전송한다. 원격 쓰기가 실제로 성공하고 응답만 유실된 경우에도 재조회 후 확인하므로 중복 삽입을 줄인다.

정상 context 종료는 `flush()`를 실행한다. 예외가 발생한 종료는 자동 재전송하지 않고 연결만 닫는다. RawTree 조회 실패를 로컬 성공으로 대체하지 않는다. 로컬 모드를 명시적으로 선택하면 로컬 저널만 조회한다.

## 시간·실험 격리

원격 기억 조회는 `run_id`, `entity_id`, `elapsed_seconds <= as_of_seconds`를 SQL에서 먼저 제한한다. 반환 결과에도 같은 조건을 적용한 후 가장 높은 `record_version`을 선택한다. 미래의 높은 버전을 먼저 선택하고 시간 필터를 적용하는 순서를 사용하지 않는다.

`elapsed_seconds`는 해당 실행에서 정보가 이용 가능해진 재생 시각이어야 한다. 미래 정보로 만든 기억에 과거 시각을 부여하면 저장 계층만으로 이를 탐지할 수 없다. 호출자는 원본 관측 순서와 모델 결과 공개 시각을 보존해야 한다. 날짜가 없는 영상에는 실제 촬영 날짜를 임의로 부여하지 않는다.

RawTree 모드는 로컬 저널이 비어 있어도 원격 데이터를 조회해 재시작 상태를 복원한다. 전체 이벤트 JSON을 보존하므로 중첩 `state`도 동일하게 돌아온다. 문자열 SQL 값은 따옴표와 역슬래시를 escape하며 테이블 이름은 고정 allowlist에서만 만든다.

## 검증 결과

2026-09-25에 다음 로컬 테스트 12개를 통과했다.

- 재시작 영속성, 시간 차단, run/entity 격리.
- 동일 ID 재시도 중복 제거와 다른 payload 충돌 검출.
- 중단된 JSONL 마지막 쓰기 복구.
- 빈 로컬 폴더에서 원격 기억 복원과 미래 버전 차단.
- 원격 쓰기 실패의 outbox 보존과 재시작 후 재전송.
- 텍스트 쓰기 응답 이후 원본 payload 재조회.
- 원격 장애 때 로컬 성공으로 대체하지 않음.
- 따옴표가 포함된 run ID의 안전한 SQL literal 처리.
- 존재가 확인된 전용 테이블의 metadata 캐시, 뒤늦게 생성된 테이블 발견, 신규 run 격리.
- 첫 삽입으로 생성된 테이블의 발견과 이후 목록 조회 생략.
- 쓰기 후 지연 가시성의 제한된 조회 재시도와 중복 insert 미실행.
- 조회 대기 초과 시 outbox 유지 및 재시작 후 재전송 전 조회 대기.

```sh
python3 -m unittest discover -s tests -p test_storage.py -v
```

실제 공식 RawTree MCP에서도 **쓰기·재조회·빈 로컬 디렉터리 재시작·미래 차단·다른 run 격리·중복 재시도**를 통과했다.

| 항목 | 실제 검증값 |
| --- | --- |
| 테이블 | `tomato_lha_memory_events` |
| 테스트 run | `storage_fixture_ee6c8c98c6584a3191237fea0216ed1e` |
| 격리 비교 run | 위 ID + `_isolated` |
| 남긴 행 | 테스트 기억 총 3건, 모두 `integration_fixture=true` |
| 기본 run의 기억 | 10초 version 1, 30초 version 2 |
| 20초 조회 | 10초 기억 반환 |
| 30초 조회 | 30초 기억 반환 |
| 9초 조회 | `None` |
| 재시작 후 같은 이벤트 재전송 | 기본 run 이벤트 2개 유지 |

이 행들은 실제 토마토 관측이나 모델 추론이 아니다. `dataset_id=integration_fixture`, `state.not_real_observation=true`로도 표시했다. 평가 데이터에 포함하지 않는다. 초기 쓰기 응답의 텍스트 형식 차이를 수정한 뒤 같은 run을 이어서 검증하여 최종 3개 fixture 행만 남겼다.

추가로 실제 `tomato_c_demo_v1` 실행의 day03 관측이 쓰기 직후 보이지 않아 남은 outbox 1건을 복구했다. 수정 후 `flush()`는 원격 조회 1회만으로 기존 행을 확인하고 pending을 1→0으로 바꿨다. 이 복구에서 insert와 모델 호출은 모두 0회였다.

## MVP 제한

- 단일 writer를 전제로 한다. `read-before-write`는 동시 writer에 대한 DB 고유성 보장이 아니다. 같은 root/run을 여러 프로세스가 동시에 쓰지 않는다.
- SQL 조회는 종류/run별 최대 10,000행이다. 상한에 도달하면 불완전한 보고를 반환하지 않고 오류를 내므로 장기 실행에는 페이지 조회가 필요하다.
- 로컬 파일의 완성된 잘못된 JSON 행은 숨기지 않고 오류를 낸다. 마지막 미완성 append만 복구한다.
- 원격 outbox 동기화는 순차적이다. 자동 백그라운드 전송이나 무한 재시도는 없다.
