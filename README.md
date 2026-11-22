# 도쿄 아리아케 아레나 항공권 트래커 (2027.03.27 ~ 03.29)

SerpApi(Google Flights) + GitHub Actions + GitHub Pages 기반의 **무료 자정 자동 항공권 트래커**입니다.
Python 3 표준 라이브러리만 사용하므로 별도 패키지 설치(`pip install`) 없이 어떤 PC에서도 폴더째 옮겨 바로 실행할 수 있습니다.

## 폴더 구조

```text
tokyo-flight-tracker/
├── index.html                           # 대시보드 UI
├── fetch_flights.py                     # SerpApi 6구간 수집기 + 무료 잔여 크레딧 조회
├── data/
│   └── flights.json                     # 수집 결과 및 일별 자정 히스토리 누적 파일
├── .github/
│   └── workflows/
│       └── update-flights.yml           # 매일 자정(00:00 KST) 자동 수집 워크플로우
├── .env.example                         # 로컬 수동 수집용 API 키 템플릿
├── .gitignore                           # .env 커밋 방지
├── start_local.bat / start_local.sh     # 다른 PC에서 대시보드 원클릭 실행
├── fetch_now.bat                        # Windows에서 로컬 수동 1회 수집
└── README.md                            # 본 가이드
```

## 1단계: SerpApi 무료 API 키 발급 (월 250회 무료)
1. [https://serpapi.com](https://serpapi.com) 회원가입 (이메일/전화번호 인증)
2. 대시보드 좌측 `Your Account` → `API Key` 복사
   - 1회 실행당 6크레딧 소모 (`ICN↔NRT`, `GMP↔HND` 왕복 2 + 편도 4)
   - 잔여 횟수 조회(`/account.json`)는 **0크레딧(무료)**
   - 하루 1회 자정 자동수집 = 월 약 180~186크레딧 사용 (월 250회 한도 내 여유)

## 2단계: GitHub에 올려 24시간 자정 자동 수집 켜기
1. GitHub에서 새 저장소 생성 (예: `tokyo-flight-tracker`, **Public** 권장 — 무료 GitHub Pages 지원)
2. 이 폴더 전체를 저장소에 업로드(Push)
3. 저장소 상단 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SERPAPI_API_KEY`
   - Secret: 1단계에서 복사한 키 붙여넣기
4. 저장소 상단 **Settings → Actions → General → Workflow permissions**
   - **Read and write permissions** 선택 후 Save
5. 저장소 상단 **Settings → Pages**
   - Source: `Deploy from a branch`, Branch: `main` / `/ (root)` 선택 후 Save
6. **Actions** 탭 → `Update Tokyo Flight Prices (Daily Midnight KST)` → **Run workflow** 클릭해 첫 수집 테스트
7. 약 1분 뒤 `https://<본인아이디>.github.io/<저장소이름>/` 접속

## 3단계: (선택) 웹페이지에서 버튼으로 즉시 수집하기
- GitHub 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens** 생성
  - 대상 저장소: `tokyo-flight-tracker`
  - Permissions → Repository permissions → **Actions: Read and write**
- 대시보드 우측 상단 **[API / GitHub 설정]**에 아이디, 저장소명, PAT 입력 후 저장

## 다른 PC에서 바로 실행하는 법 (로컬 실행)
1. `tokyo-flight-tracker` 폴더를 그대로 복사합니다.
2. **대시보드 열기:** `start_local.bat` (Windows) 또는 `./start_local.sh` (Mac/Linux) 실행 → `http://localhost:8000` 자동 오픈
3. **로컬 수동 수집:** `.env.example`을 복사해 `.env`로 이름 변경 후 `SERPAPI_API_KEY` 입력 → `fetch_now.bat` 또는 `python fetch_flights.py` 실행
