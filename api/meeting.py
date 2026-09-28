"""Dooray /ai 요청을 GitHub Issue 기반 개인 PC 작업 큐에 등록한다."""

from __future__ import annotations

import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request

from api.common import pack


router = APIRouter()
GITHUB_API = "https://api.github.com"
JOB_FILE_PREFIX = "meeting_job_"
ISSUE_PREFIX = "[meeting-job]"
DEFAULT_GITHUB_REPO = "gilnyangyi-test/dooraybot"


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def normalize_query(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^/ai(?:\s+|$)", "", value, flags=re.IGNORECASE).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def contains_mutation_request(query: str) -> bool:
    return bool(
        re.search(
            r"예약(?:을)?\s*(?:해|신청|취소|삭제|변경)|(?:신청|취소|삭제)해\s*줘",
            query,
        )
    )


def job_file_name(job_id: str) -> str:
    return f"{JOB_FILE_PREFIX}{job_id}.json"


async def enqueue_job(
    client: httpx.AsyncClient,
    token: str,
    repo: str,
    job: dict[str, Any],
) -> int:
    headers = github_headers(token)
    filename = job_file_name(job["job_id"])
    gist_response = await client.post(
        f"{GITHUB_API}/gists",
        headers=headers,
        json={
            "description": f"meeting-job:{job['job_id']}",
            "public": False,
            "files": {filename: {"content": json.dumps(job, ensure_ascii=False, indent=2)}},
        },
    )
    gist_response.raise_for_status()
    gist_id = str(gist_response.json()["id"])
    gist_url = f"{GITHUB_API}/gists/{gist_id}"

    try:
        issue_response = await client.post(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers=headers,
            json={
                "title": f"{ISSUE_PREFIX} {job['job_id']}",
                "body": "Dooray 회의실 조회 작업입니다. 실제 요청 데이터는 요청별 비공개 Gist에 저장됩니다.",
            },
        )
        issue_response.raise_for_status()
    except Exception:
        await client.delete(gist_url, headers=headers)
        raise
    issue_number = int(issue_response.json()["number"])
    return issue_number


@router.post("/dooray/ai")
async def meeting_command(req: Request):
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    expected_app_token = os.environ.get("DOORAY_APP_TOKEN", "")
    if not all((github_token, repo, expected_app_token)):
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ 회의실 봇의 서버 환경변수가 완성되지 않았습니다.",
        })

    data = await req.json()
    supplied_app_token = str(data.get("appToken") or "")
    if not hmac.compare_digest(supplied_app_token, expected_app_token):
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ 유효하지 않은 Dooray 요청입니다.",
        })

    query = normalize_query(str(data.get("text") or ""))
    if not query:
        return pack({
            "responseType": "ephemeral",
            "text": '사용법: /ai "10월 1일 예약 현황을 알려줘"',
        })
    mutation_requested = contains_mutation_request(query)

    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "status": "queued",
        "query": query,
        "trigger_id": str(data.get("triggerId") or ""),
        "user_id": str(data.get("userId") or ""),
        "channel_id": str(data.get("channelId") or ""),
        "mutation_requested": mutation_requested,
        "created_at": now.isoformat().replace("+00:00", "Z"),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            issue_number = await enqueue_job(client, github_token, repo, job)
    except Exception as exc:
        return pack({
            "responseType": "ephemeral",
            "text": f"⚠️ 회의실 조회 요청을 등록하지 못했습니다: {type(exc).__name__}",
        })

    return pack({
        "responseType": "inChannel",
        "text": (
            f'회의실 예약 요청을 처리 중입니다. (약 1분 소요)\n질의 : "{query}"'
            if mutation_requested
            else f'회의실 정보를 조회 중입니다. (약 1분 소요)\n질의 : "{query}"'
        ),
    })
