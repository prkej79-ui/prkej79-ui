# 국내여행 챗봇 배포본

이 폴더에는 실행에 필요한 Python 모듈, CSS, 배경 이미지와 라이브러리 목록만 들어 있습니다. 원본 프로젝트는 상위 폴더에 보존되어 있습니다.

## 실행

Python 3.12 환경에서 이 폴더를 작업 디렉터리로 사용하세요.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

로컬에서 실행할 때는 `.env.example`을 `.env`로 복사하고 값을 입력합니다. 기존 원본 폴더의 `.env`는 자동으로 읽지 않습니다.

```powershell
Copy-Item .env.example .env
```

배포 서비스에서는 비밀 설정 또는 환경 변수에 아래 값을 등록합니다. 실제 키가 든 `.env` 파일은 GitHub에 업로드하지 마세요.

| 환경 변수 | 용도 |
| --- | --- |
| `OPENAI_API_KEY` | 필수: OpenAI 모델 호출 |
| `KAKAO_REST_API_KEY` | 필수: 장소 및 웹 검색 |
| `KAKAO_JAVASCRIPT_KEY` | 선택: 카카오내비 실행. 배포 도메인 등록 필요 |
| `LANGSMITH_TRACING` | 선택: 추적 사용 시 `true`, 기본값 `false` |
| `LANGSMITH_API_KEY` | LangSmith 추적 사용 시 필요 |
| `LANGSMITH_PROJECT` | LangSmith 프로젝트 이름 |

이 폴더의 내용만 저장소 최상위에 올리면 실행 파일 경로는 `app.py`입니다. 프로젝트 전체와 함께 `deploy` 하위 폴더로 올리면 실행 파일 경로는 `deploy/app.py`이며, 의존성 파일은 `deploy/requirements.txt`입니다. 배포 서비스의 작업 디렉터리와 파일 경로 설정에 맞춰 선택하세요.

복사본은 원본 수정 시 자동 갱신되지 않습니다. 이번 작업에서는 파일 준비와 로컬 화면 확인까지만 수행하며, 인터넷 서비스 배포는 별도 단계입니다.
