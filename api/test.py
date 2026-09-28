"""Dooray /test 요청을 브라우저 브리지용 고정 비공개 Gist의 job.json에 덮어쓴다.

사내 브리지 서버가 이 Gist를 주기적으로 조회하다가 job_id가 바뀌면 새 작업으로 처리한다.

필요한 환경변수
- GITHUB_TOKEN: Gist 쓰기 권한이 있는 토큰
- BRIDGE_GIST_ID: 작업을 기록할 비공개 Gist ID
- DOORAY_APP_TOKEN: 기존 Dooray 슬래시 커맨드 앱 토큰
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request

from api.common import pack


router = APIRouter()
GITHUB_API = os.environ.get("GITHUB_API_BASE", "https://api.github.com")
JOB_FILE_NAME = "job.json"
MAX_TEXT_LENGTH = 500


@router.post("/dooray/test")
async def test_command(req: Request):
    github_token = os.environ.get("GITHUB_TOKEN", "")
    gist_id = os.environ.get("BRIDGE_GIST_ID", "")
    expected_app_token = os.environ.get("DOORAY_APP_TOKEN", "")
    if not github_token or not gist_id or not expected_app_token:
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ /test 서버 환경변수(GITHUB_TOKEN, BRIDGE_GIST_ID, DOORAY_APP_TOKEN)가 설정되지 않았습니다.",
        })

    data = await req.json()
    supplied_app_token = str(data.get("appToken") or "")
    if not hmac.compare_digest(supplied_app_token, expected_app_token):
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ 유효하지 않은 Dooray 요청입니다.",
        })

    text = str(data.get("text") or "").strip()[:MAX_TEXT_LENGTH]
    job_id = uuid.uuid4().hex
    # 로컬 브리지가 비동기 분석 결과를 원래 요청자에게 돌려주기 위해 Dooray의 일회성 responseUrl을 전달한다.
    # appToken은 절대 저장하지 않는다. Gist는 반드시 비공개로 운영해야 한다.
    job = {
        "job_id": job_id,
        "command": str(data.get("command") or "/test"),
        "text": text,
        "user_id": str(data.get("userId") or ""),
        # Dooray는 사용자 이름 대신 userEmail을 전달한다. 최종 응답에서는 브라우저 확장이 확인한
        # 로그인 사용자 이름을 우선 사용하고, 연결이 끊긴 경우 이 값을 보완 표시로 쓴다.
        "user_email": str(data.get("userEmail") or ""),
        "channel_id": str(data.get("channelId") or ""),
        "tenant_id": str(data.get("tenantId") or ""),
        "response_url": str(data.get("responseUrl") or ""),
        # 대체 전송 경로(채널 콜백)용. 값은 민감하므로 비공개 Gist 유지가 필수.
        "tenant_domain": str(data.get("tenantDomain") or ""),
        "cmd_token": str(data.get("cmdToken") or ""),
        "trigger_id": str(data.get("triggerId") or ""),
        # 진단용: Dooray가 실제로 보낸 필드 '이름'만 기록(값 아님). response_url 필드명 확인용.
        "dooray_fields": sorted(data.keys()),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 새 Gist를 만들지 않고 고정 Gist의 job.json만 덮어쓴다.
            response = await client.patch(
                f"{GITHUB_API}/gists/{gist_id}",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={
                    "files": {
                        JOB_FILE_NAME: {
                            "content": json.dumps(job, ensure_ascii=False, indent=2)
                        }
                    },
                },
            )
            response.raise_for_status()
    except Exception as exc:
        return pack({
            "responseType": "ephemeral",
            "text": f"⚠️ 요청을 등록하지 못했습니다: {type(exc).__name__}",
        })

    shown = text
    if len(shown) >= 2 and (shown[0], shown[-1]) in {('"', '"'), ("'", "'"), ("“", "”")}:
        shown = shown[1:-1].strip()
    requester = str(data.get("userEmail") or data.get("userId") or "알 수 없음")
    return pack({
        "responseType": "inChannel",
        "replaceOriginal": False,
        "text": (
            "📥 **업무 비서 요청 접수**\n"
            f"- 요청자: {requester}\n"
            f"- 요청 내용: {shown or '(내용 없음)'}\n"
            f"- 작업 ID: {job_id[:8]}"
        ),
    })
