# 실제 토마토 18일 시계열 데이터

주 시연 데이터는 [Zenodo 21943147](https://zenodo.org/records/21943147)의 **같은 토마토 한 개를 18일 동안 촬영한 실제 RGB 사진 18장**이다. 원본 PNG 18개와 원본 XLSX를 내려받았으며 전체 5,160,730바이트, 19개 파일 모두 Zenodo가 제공한 MD5와 일치한다. 라이선스는 **CC BY 4.0**, 제공자는 Elvianto Hartono, DOI는 `10.5281/zenodo.21943147`이다.

이는 저장 중 외관 변화 시연용 단일 개체 데이터다. 18장은 독립적인 18개 토마토가 아니며, 감염 여부·병명·생리적 신선도·섭취 안전성 정답은 제공되지 않는다. 모델의 문장이나 영상상의 변화를 새 병리 정답으로 만들지 않는다.

## 바로 사용할 파일

- 실행 입력: `data/samples/tomato_18day/observations.jsonl`
- 원본 이미지: `data/samples/tomato_18day/frames/RGB_01.png`부터 `RGB_18.png`
- 원본 상태 자료: `data/samples/tomato_18day/source/Tomato_RGB_UV_Data_Availability.xlsx`
- 출처·라이선스·파일별 SHA256/MD5: `data/samples/tomato_18day/provenance.json`
- 원본 API 메타데이터: `data/catalog/tomato/zenodo_21943147.json`
- Nimble 원문 검증: `data/catalog/tomato/nimble/20260925T215658529501Z/request_00.json`

최초 자료 지목은 사용자 작업 맥락에서 이루어졌고, 원문 확인은 Nimble, 파일 목록·라이선스·체크섬 확인은 Zenodo 공개 API, 바이너리 다운로드는 직접 HTTPS로 수행했다. Nimble 응답 자체를 이미지 데이터로 간주하지 않는다.

```sh
python3 scripts/collect_tomatoes.py
```

수집기는 최대 네 파일을 병렬로 받는다. 요청당 30초, 최대 두 번 시도하고, 파일 크기 및 MD5를 확인한 뒤 저장한다. 검증된 로컬 파일이 있으면 재사용한다. 전체 선택 데이터는 100 MiB 미만으로 제한한다. XLSX는 변경하지 않고 표준 Python ZIP/XML로 원시 환경값만 읽는다.

## 입력 계약과 상태값

`dataset_id=zenodo_tomato_18day_21943147`, `dataset_version=21943147`, `sequence_id=tomato_18day_specimen_01`, `entity_id=tomato_01`로 고정했다. 관측 ID는 `tomato_18day_day_01`부터 `_18`이다. `frame_uri`는 저장소 루트 기준 상대 경로다.

`elapsed_seconds`는 일차 순서로부터 계산한 상대 축이다. 1일차는 0초, 18일차는 1,468,800초다. 절대 촬영 시각은 원본에서 확인되지 않아 모든 `observed_at`은 `null`이다. 정밀한 촬영 간격이나 시각을 추가 추정하지 않는다. 모든 행에서 `synthetic=false`, `disease_label=null`이다.

| `state` 필드 | 실제 원본 | 단위·주의점 |
| --- | --- | --- |
| `storage_day` | `Environment_Context`의 `Day` | 1–18일 관측 인덱스 |
| `temperature_c` | `Temperature_C` | °C |
| `relative_humidity_pct` | `RelativeHumidity_pct` | % |
| `eco2_ppm` | `eCO2_ppm` | SGP30의 등가 CO₂ 출력. 기준급 직접 CO₂ 측정값이 아님 |
| `tvoc_ppb` | `TVOC_ppb` | SGP30의 총휘발성유기화합물 센서 출력 |

`Environment_Context!A4:E21`을 `Day`로 정확히 연결했다. 각 JSONL 행의 `state_source`에 원본 파일·시트·행 범위가 있다. 이 네 환경값은 원본 연구에서 맥락 자료로 제공한 값이며 질병 정답이 아니다. 원본의 일부 상관계수 파생 시트에는 캐시된 `#NAME?` 오류가 있어, 해당 계산값은 입력하지 않았다. 원시 환경값 18행은 모두 숫자이며 별도 `openpyxl` 읽기 결과와 일치한다.

## 검증 범위

18개 PNG의 디코딩·SHA256, 원본 파일 19개의 MD5, 고유 관측 ID, 일차 순서, 상대 시간, XLSX 상태값 대응을 검증했다. 첫날과 마지막 날 사진도 직접 확인했다. 병리 평가나 조기진단 성능 검증은 수행하지 않았다. 같은 단일 개체의 사진을 임의로 나눠 일반화 성능으로 보고하면 안 된다.

## TR-6 추가 자료: 큰 ZIP에서 토마토만 선택 가능

[TriModal Ripeness 6](https://figshare.com/articles/dataset/30783827), DOI `10.6084/m9.figshare.30783827.v1`, 라이선스 **CC BY 4.0**도 공식 Figshare API로 확인했다. 전체 자료는 단일 `TR-6.zip`, 20,388,430,589바이트다. 전체 ZIP은 내려받지 않았다.

서버의 HTTP Range 지원을 실제로 확인하고 ZIP64 꼬리와 중앙 디렉터리만 읽었다. 전송량은 **2,754,017바이트**다. 토마토 경로의 9,183개 항목(디렉터리 10개 포함)을 `data/catalog/tomato/tr6_tomato_file_index.json`에 저장했다. `Normal/Tomato/sRGB_images`에는 디렉터리를 제외한 2,244개 JPG가 있으며, IR-fusion 및 methane TXT도 있다. `Classified`에는 `Not_spoiled`/`Spoiled` 구조가 있으나 `Normal`과 중복될 수 있다.

예시 이름 `TR-6/Normal/Tomato/sRGB_images/20250723_092034.jpg`는 촬영 시각 형식을 담고 있다. 다만 이 목록만으로 물리적 개체 ID, 센서와 이미지의 정확한 대응, 클래스별 실험 절차를 확정하지 않았다. 이 단계에서는 TR-6 이미지·센서 본문을 받거나 주 시연 manifest에 합치지 않았다. 향후 ZIP 중앙 디렉터리의 파일 오프셋을 이용해 토마토 일부만 가져오는 방법은 기술적으로 가능하며, 추출 시 ZIP CRC와 원본 메타데이터를 추가 검증해야 한다.

Figshare의 Nimble 페이지 추출은 HTTP 500으로 실패했다. TR-6의 위 파일 목록·라이선스·범위 다운로드 결과는 **공식 API 및 실제 Range 요청에서 확인한 결과**다.
