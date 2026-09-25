# 사과 성능검증 데이터 출처 감사

검사일: 2026-09-25. 모델 추론 없이 출처와 다운로드 파일 구조를 확인했다. 이 감사의 사과 실험은 토마토에 대한 성능 근거가 아니다.

## 현재 검증 가능한 범위

**정적 사과 사진에서 눈에 보이는 정상/부패 구분을 외부 데이터로 시험할 수 있다. 동일 사과의 질병 조기탐지 성능을 측정할 공개 시계열은 이번 제한된 조사에서 확보하지 못했다.** 이는 그런 데이터가 존재하지 않는다는 뜻이 아니다.

기존 [Nimble 카탈로그](../../data/catalog/README.md)를 검토한 뒤, 실제 Nimble API로 검색 2회와 원문 추출 3회를 실행했다. 다섯 요청 모두 성공하고 내용을 반환했다. 초기 샌드박스 검색 2회는 전송 실패했으며 성공 실적에 포함하지 않는다. 검색 결과와 추출 원문은 [source_research](source_research)에 보존했다. 데이터셋 파일 목록과 ZIP 중앙 디렉터리는 별도의 공개 HTTP 요청으로 검증했다. Nimble 검색 자체가 이미지 다운로드나 라이선스 검증을 대신하지 않는다.

## 독립 외부 검증용 데이터

[Fresh and Rotten Fruits Dataset for Machine-Based Evaluation of Fruit Quality](https://data.mendeley.com/datasets/bdd69gyhv8/1), DOI `10.17632/bdd69gyhv8.1`.

- 저자: Nusrat Sultana, Musfika Jahan, Mohammad Shorif Uddin. 게시일 2022-04-08.
- 원문에서 **CC BY 4.0**, 사과를 포함한 16종류의 과일/상태 클래스, 농업 기관 전문가의 정상/부패 라벨 지원을 확인했다.
- 원본 3,200장과 별도로 증강 이미지가 있다. 증강 ZIP은 사용하지 않는다.
- 공개 파일 메타데이터와 원본 ZIP 중앙 디렉터리에서 `Original Image/FreshApple`의 JPEG 200장, `Original Image/RottenApple`의 JPEG 200장을 확인했다.
- 원본 ZIP 전체는 2,794,170,228 bytes이지만 HTTP 206 범위 읽기를 지원한다. 따라서 원본 파일 40장의 압축 페이로드 합계 45,829,919 bytes만 선택해 획득할 수 있다. 전체 ZIP은 다운로드하지 않는다.
- **고정 선택:** Python `random.Random(20260925)`, 클래스 내 원본 경로 사전순 정렬 후 FreshApple 20장, RottenApple 20장 균등 무작위 추출. 사진을 보거나 모델 결과를 이용한 선별 없이 [선택 목록](external/selection.json)을 먼저 저장했다.
- 기존 주 실험 데이터 `y7gktb2wwb/1`과 다른 출처다. 원본 출처의 독립성과 평가 시 exact SHA256 중복 검사는 확인 가능하지만, 실제 과실 ID나 근접 중복까지 독립이라고 보장할 수 없다.
- 코드 호환을 위해 `FreshApple → healthy`, `RottenApple → infected`로 매핑한다. **여기서 infected는 부패 라벨을 담는 내부 명칭이며 병원체 감염 확진을 의미하지 않는다.**
- 원본 파일별 CRC32, 바이트 수를 ZIP 메타데이터와 대조하고 SHA256을 계산한다. 일부 파일만 받으므로 전체 ZIP SHA256은 검증했다고 주장하지 않는다.

**획득 결과:** 40장, 원본 JPEG 합계 46,753,161 bytes. 40개의 SHA256은 모두 서로 다르며, 현재 주 실험 200장과 초기 실험 4장 총 204개 파일과 exact SHA256 중복은 0개였다. manifest는 외부 모델 추론 전에 생성했다. 파일 수준 중복 검사이며 동일 과실 또는 비슷한 사진까지 배제한 결과는 아니다.

추출 근거: [Nimble 원문](source_research/20260925T215958503116Z/request_00.json), [공개 파일 메타데이터](source_research/bdd69gyhv8_files.json), [원본 ZIP 파일 목록](source_research/bdd69gyhv8_full_index.json), [외부 샘플 manifest](external/manifest.json), [획득 스크립트](external/download.py).

## 시계열 및 대체 후보 판단

| 후보 | 실제 확인된 것 | 사용 한계 |
| --- | --- | --- |
| [같은 Fuji 사과 갈변 영상](https://commons.wikimedia.org/wiki/File:Browning_Fuji_apple_-_32_minutes_in_16_seconds.webm) | 기존 카탈로그에서 동일 절단 과실, 1분 간격 32개 원본 사진, CC BY-SA 4.0, 작은 WebM 획득 기록 확인 | 상대 시각 0–31분을 사용하는 산화 재생 데모. 질병 라벨·건강 대조군·감염 시작점 없음. 조기진단 성능 평가 불가 |
| [FruitVision v2](https://data.mendeley.com/datasets/xkbjx8959c/2) | Nimble 원문에서 사과 포함 fresh/rotten/formalin 클래스, 원본 및 증강 설명, CC BY-NC-ND 4.0 확인 | 동일 과실 ID/관측 시각 미확인. 이번 외부 검증에는 사용하지 않음 |
| [FruQ-DB](https://zenodo.org/records/7224690) | Nimble 원문에서 타임랩스 유래, fresh/mild/rotten, CC BY 4.0 확인 | 설명에 사과가 없어서 사과 대상에서 제외. 동영상 원본과 가공본 라이선스 관계·실제 시간축도 추가 확인 필요 |

**조기진단 검증에 아직 필요한 데이터:** 여러 독립 사과 ID, 동일 개체의 연속 RGB 관측, 취득 시각 또는 경과 시간, 라벨의 근거와 이상 발생 구간, 정상 대조군, 재사용 라이선스. 파일 이름 순서를 시간으로 가정하거나 서로 다른 정상/부패 사과를 이어 붙여 조기진단 정답을 만들지 않는다.

현재 성능 실험은 정적 외관 분류와 강한 모델로 넘겨야 할 후보의 재현율·오탐·호출비율을 평가할 수 있다. 실제 과실 진행, 조기 탐지 시간, 장기 기억에 의한 탐지 향상과 토큰 절감은 별도 검증 과제로 남는다.
