### Plan
https://luma.com/horizonagentshack
여기서 우리는 Tinybird를 잘 활용하는 것을 메인으로 할 꺼임.

### Notion page
https://app.notion.com/p/Hackrathon-long-horizon-3e62a46dc68c80e88141e4af42926bf4?source=copy_link



### 현재 확정 구성

**토마토 + Liquid 저비용 관측 + GPT-5 정밀 분석**으로 진행한다. 전체 문제 정의·아키텍처·실험 계획은 [final_plan.md](final_plan.md)에 정리한다.

```text
토마토 관측 → 매번 Liquid로 특징·품질 추출
                                    ↓
                 Controller: RawTree 기억 + 명시적 규칙
                       ↓                        ↓
              저비용 분석으로 종료       GPT-5 정밀 분석 추가
                       └──── 결과·미해결 질문·다음 계획 저장 ────┘
```

| 구성 | 역할 | 현재 상태 |
| --- | --- | --- |
| Liquid `LFM2.5-VL-1.6B` | 로컬 이미지 특징·이상 후보 추출 | 설치·사과 4장 실험 완료. 토마토 검증 전 |
| Controller | 외부 기억·규칙으로 분석 수준 결정 | 보호 규칙 프로토타입 있음. 통합 런타임 구현 전 |
| OpenAI `gpt-5` | 원본 이미지·과거 근거를 이용한 정밀 분석 | 요청 모델 확정. 프로젝트 실제 호출 전 |
| Tinybird RawTree MCP | 관측·미해결 질문·계획·사용량 저장 | 실제 인증·조회·사과 카탈로그 쓰기/재조회 검증 완료 |
| Nimble | 토마토 데이터 검색·원문 검증 | 실제 호출 성공. `data/catalog/tomato_quick/`에 검색 기록 |
| BFL | 선택적 합성 시나리오 | 키 대기 |

분석 경로는 `LOW_COST_ONLY`와 `HIGH_COST_ANALYSIS` 두 가지다. 양쪽 모두 Liquid를 실행하고 사진·관측·기억을 저장하며, 고비용 경로에만 GPT-5를 추가한다. Liquid의 `next_action`을 그대로 실행하지 않는다. 새로운 이상·불확실성·지속/확대된 변화·미해결 질문의 기한/조건 도달·최초 관측·최대 정밀 분석 공백을 외부 규칙이 확인한다. RGB 차이만으로 결정하지 않는다. 품질 불량은 `quality_status`와 `review_required`로 별도 기록하고 재촬영을 요청하며, 이를 정상이나 변화 없음으로 처리하지 않는다. Liquid가 관측을 했다는 이유로 마지막 정밀 분석 시각을 갱신하지 않는다. 정상 출력도 정상 확진으로 저장하지 않는다.

활성 저비용 모델은 Liquid이며 GPT-4.1-mini는 제외한다. “GPT 5.0”의 API ID는 `gpt-5`다. GPT-5 연결 시 `.env`의 표준 `OPENAI_API_KEY`와 기존 `OPEN_AI_API_KEY` 별칭을 지원하도록 설계한다. `.env`는 Git에서 제외한다.

### Liquid 채택 근거

[실험 보고서](liquid/README.md)의 사과 4장 측정에서 512px 입력 중앙값 2.19초/장, 최대 관측 서버 RSS 1.33 GiB, 추론 API 청구액 $0을 확인했다. 행동 선택·미해결 기억 처리에는 실패가 있어 외부 Controller로 분리한다. 토마토 정확도·조기탐지·전체 운영 비용은 검증되지 않았다.

설정은 `Q4_K_M` 본체 + `Q8_0` projector, llama.cpp `b11191`, 최대 변 512px, image-max-tokens 256을 초기값으로 사용한다. 기존 `liquid/benchmark.py`는 사과 실험 재현용이다.

### 토마토 데이터 계획

- [18일 관측](https://zenodo.org/records/21943147): 동일 토마토 1개, RGB 18장·UV 18장. 첫 재생 데모 후보. 공개 파일 목록 확인, 로컬 수집·라이선스 확인 대기.
- [TR-6](https://pmc.ncbi.nlm.nih.gov/articles/PMC12925515/): 주 실험 후보. 토마토 RGB 2,244장·열화상 2,341장과 가스 기록. 개체·시각·각도·중복·라벨·라이선스를 파일에서 확인한 뒤 채택한다.
- 기존 사과 데이터와 실험 결과는 역사적 검증 자료로 보존하며 토마토 평가에 섞지 않는다.

토마토용 신규 RawTree 테이블은 `tomato_lha_` 접두사를 사용한다. 기존 `apple_lha_dataset_catalog`를 토마토 테이블로 바꾸지 않는다. [기억 이벤트 계약](docs/tinybird_memory.md)을 따른다.

### 비교 실험

| 실험군 | 동작 |
| --- | --- |
| A | 모든 관측을 GPT-5로 분석 |
| B | 매 관측 Liquid 실행 → GPT-5 추가 여부 선택. 의미 있는 장기 기억 없음 |
| C | 매 관측 Liquid 실행 → RawTree 장기 기억·규칙으로 GPT-5 추가 여부 선택 |

A/C로 전체 선택적 분석 효과, B/C로 기억의 추가 효과를 평가한다. GPT-5 호출 수·클라우드 API 비용·모델별 토큰·로컬 실행 시간과 함께 미탐·오탐·탐지 지연을 비교한다. 메모리 요약 등 부가 모델 호출도 계측한다. Liquid 토큰을 GPT-5 토큰과 같은 금액으로 합산하지 않는다.

활성 설계의 스폰서는 Liquid·Tinybird·Nimble 세 곳이다. 실제 사용 기록은 있으나 대회 인정 여부와 토마토 통합 데모 완료는 별도 확인한다. BFL은 선택적으로 추가한다.

### 다음 구현 순서

1. 토마토 시퀀스를 수집하고 동일 개체·시간·라벨·라이선스를 검증한다.
2. Liquid 관측 출력을 토마토에서 확인하고 보호 규칙과 연결한다.
3. GPT-5 원본 이미지 분석과 실제 사용량을 검증한다.
4. RawTree 기억·미해결 질문·후속 계획과 재시작 복원을 연결한다.
5. 같은 스트림으로 A/B/C를 비교한다.

### 기존 검증 재현

```sh
# 기존 Liquid 사과 실험의 규칙 검사 (모델 호출 없음)
python3 -m unittest discover -s liquid -p 'test_*.py'
# 로컬 키·실행 파일 확인 (네트워크 없음)
python3 scripts/rawtree_mcp_stdio.py --check
# 실제 MCP 읽기 검증
python3 scripts/rawtree_mcp_probe.py
# 토마토 검색 계획 확인 (네트워크 없음; 수집기 파일명은 기존 이름 유지)
python3 scripts/nimble_collect_apples.py --out data/catalog/tomato_quick --dry-run --query 'tomato spoilage longitudinal RGB image dataset same fruit timestamps'
```

Codex `rawtree` MCP는 `scripts/rawtree_mcp_stdio.py`로 `.env`의 RawTree 설정을 공식 `@rawtree/mcp@0.3.2`에 전달한다. 키를 명령행·설정 파일·로그에 기록하지 않는다. 이 문서 갱신은 새 모델 추론이나 원격 데이터 쓰기를 실행하지 않는다.
