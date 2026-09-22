# Dooray `/ai` 회의실 조회 봇

## 동작 구조

1. Dooray `/ai`가 `POST /dooray/meeting`을 호출합니다.
2. Vercel은 실제 요청을 비공개 Gist의 `meeting_jobs.json`에 저장합니다.
3. 공개 GitHub 저장소의 Issue에는 무작위 작업 ID만 등록합니다.
4. 개인 PC의 `worker/meeting_worker.py`가 Issue를 감지합니다.
5. 작업자가 개인 PC의 회의실 API를 호출하고 `responseUrl`로 결과를 보냅니다.
6. 작업 완료 후 Issue를 닫습니다.

개인 PC에는 인바운드 포트 개방이 필요하지 않습니다.

## Vercel 환경변수

Vercel 프로젝트 Settings → Environment Variables에 다음 값을 설정합니다.

- `GITHUB_TOKEN`: Gist 수정 및 Issue 생성 권한이 있는 GitHub 토큰
- `GIST_ID`: 작업 정보를 저장할 비공개 Gist ID
- `GITHUB_REPO`: `owner/repository` 형식의 Issue 저장소
- `DOORAY_APP_TOKEN`: Dooray 슬래시 커맨드 설정에 표시되는 App Token

환경변수 변경 뒤에는 새로 배포해야 합니다.

## Vercel 반영 파일

- `api/meeting.py` — 새 파일
- `api/index.py` — meeting 라우터 등록
- `.env.example` — 환경변수 예시
- `MEETING_BOT_SETUP.md` — 운영 안내

`requirements.txt`와 `vercel.json`은 기존 설정으로 동작하므로 변경하지 않습니다.

## Dooray 슬래시 커맨드

- Command: `/ai`
- Request URL: `https://dooraybot.vercel.app/dooray/meeting`
- Method: `POST`

예시:

```text
/ai "10월 1일 예약 현황을 알려줘"
```

예약 신청·취소 요청은 Vercel 단계에서 거부합니다.

## 개인 PC 작업자

1. `.env.worker.example`을 참고해 `.env.worker`를 작성합니다.
2. 기존 회의실 웹 서버가 실행 중인지 확인합니다.
3. `run_meeting_worker.bat`을 실행합니다.

한 번만 확인하려면:

```powershell
python worker/meeting_worker.py --once
```

실제 처리 없이 감지만 확인하려면:

```powershell
python worker/meeting_worker.py --once --dry-run
```

작업자는 기본적으로 15초 간격으로 Issue를 확인합니다. Windows 로그인 시 자동 실행이 필요하면 `run_meeting_worker.bat`을 작업 스케줄러에 등록합니다.

## 보안 주의

- `.env.local`과 `.env.worker`는 Git에 커밋하지 않습니다.
- 공개 Issue에는 질문, 사용자 정보, Dooray `responseUrl`을 기록하지 않습니다.
- GitHub 토큰이 노출되면 즉시 폐기하고 새로 발급합니다.
- 공개 저장소의 임의 Issue는 비공개 Gist에 동일한 작업 ID가 없으면 실행하지 않습니다.
- Dooray 요청은 `DOORAY_APP_TOKEN`이 일치할 때만 접수합니다.
