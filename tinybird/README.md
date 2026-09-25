# RawTree MCP 기억 설계

[토마토 관측·기억 이벤트 계약](../docs/tinybird_memory.md)을 기준으로 RawTree MCP 연동을 준비한다. 폴더명은 기존 작업 경로를 유지했다.

사용자가 요청한 제품은 **RawTree (a Tinybird product)**다. 일반 Tinybird MCP의 `SELECT 1` 성공은 RawTree 연결 증거가 아니다. RawTree 공식 stdio MCP로 인증·도구 37개 조회·`SELECT 1 → 1`·테이블 목록을 확인했다. `apple_lha_dataset_catalog`에 실제 사과 샘플 메타데이터 1건 저장과 재조회도 성공했다. 쓰기·읽기 증거는 `data/catalog/rawtree/catalog_insert.json`, `catalog_read.json`이다. 증거는 `data/catalog/rawtree/stdio_connection.json`이다. 기존 사과 샘플과 `apple_lha_dataset_catalog`는 역사적 검증 기록으로 보존한다. 활성 토마토 설계에는 신규 `tomato_lha_` 접두사를 사용하며 기존 테이블을 삭제·이름 변경하지 않는다.

- 저비용 특징 추출: 매 관측 로컬 Liquid `LFM2.5-VL-1.6B` 실행. 결과는 모델 추정으로 기록.
- 분석 경로: `LOW_COST_ONLY`(Liquid로 종료) / `HIGH_COST_ANALYSIS`(Liquid 후 GPT-5 추가). RawTree 기억과 규칙이 선택하며 Liquid `next_action`은 실행에 사용하지 않음.
- 정밀 판독: 규칙이 선택한 경우에만 OpenAI `gpt-5` 추가 호출. 두 경로 모두 사진·관측·기억을 저장하며 재촬영은 품질 플래그와 후속 과제로 관리.
- 읽기: RawTree MCP `run-query`.
- 쓰기: RawTree MCP `insert-json` / `insert-from-url`, 필요 시 RawTree SDK/API.
- 이미지: 로컬 또는 별도 오브젝트 저장소. DB에는 참조만 기록.
- 기억: `run_id`로 격리하고 `as_of` 이하 이벤트에서 최신 버전 구성. 관측 사실·모델 추정·검토 결과와 정책 결정을 구분.
- 형태: RawTree 동적 JSON 테이블. 일반 Tinybird `.datasource`/`.pipe` 배포는 진행하지 않음.

토마토 전용 테이블·모델 추론·기억 복원·정책 루프는 아직 검증 전이다. 이번 갱신에서는 원격 호출이나 데이터 수집을 실행하지 않았다.

[공식 RawTree MCP 연결 안내](https://rawtree.com/docs/reference/mcp)
