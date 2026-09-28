"""Dooray /test 요청을 브라우저 브리지용 비공개 Gist 작업으로 등록한다."""

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
JOB_DESCRIPTION_PREFIX = "dooray-bridge-job:"
JOB_FILE_NAME = "job.json"
MAX_TEXT_LENGTH = 500


@router.post("/dooray/test")
async def test_command(req: Request):
    github_token = os.environ.get("GITHUB_TOKEN", "")
    expected_app_token = os.environ.get("DOORAY_TEST_APP_TOKEN", "")
    if not github_token or not expected_app_token:
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ /test 서버 환경변수가 설정되지 않았습니다.",
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
    # responseUrl과 appToken 같은 민감 값은 GitHub에 저장하지 않는다.
    job = {
        "job_id": job_id,
        "command": str(data.get("command") or "/test"),
        "text": text,
        "user_id": str(data.get("userId") or ""),
        "channel_id": str(data.get("channelId") or ""),
        "tenant_id": str(data.get("tenantId") or ""),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{GITHUB_API}/gists",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={
                    "description": f"{JOB_DESCRIPTION_PREFIX}{job_id}",
                    "public": False,
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

    shown = f' "{text}"' if text else ""
    return pack({
        "responseType": "ephemeral",
        "text": f"요청을 접수했습니다.{shown}\n작업 ID: {job_id[:8]}",
    })
