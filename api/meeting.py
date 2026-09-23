"""Dooray /ai 요청을 GitHub Issue 기반 개인 PC 작업 큐에 등록한다."""

from __future__ import annotations

import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request

from api.common import pack


router = APIRouter()
GITHUB_API = "https://api.github.com"
JOB_FILE = "meeting_jobs.json"
ISSUE_PREFIX = "[meeting-job]"
JOB_TTL_HOURS = 24
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


def read_jobs(gist_data: dict[str, Any]) -> dict[str, Any]:
    file_data = gist_data.get("files", {}).get(JOB_FILE)
    if not file_data:
        return {"version": 1, "jobs": {}}
    try:
        parsed = json.loads(file_data.get("content") or "{}")
    except json.JSONDecodeError:
        return {"version": 1, "jobs": {}}
    if not isinstance(parsed.get("jobs"), dict):
        parsed["jobs"] = {}
    parsed["version"] = 1
    return parsed


def prune_jobs(document: dict[str, Any]) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=JOB_TTL_HOURS)
    retained: dict[str, Any] = {}
    for job_id, job in document.get("jobs", {}).items():
        try:
            created = datetime.fromisoformat(str(job.get("created_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created >= cutoff or job.get("status") in {"queued", "processing"}:
            retained[job_id] = job
    document["jobs"] = retained


async def enqueue_job(
    client: httpx.AsyncClient,
    token: str,
    gist_id: str,
    repo: str,
    job: dict[str, Any],
) -> int:
    headers = github_headers(token)
    gist_url = f"{GITHUB_API}/gists/{gist_id}"
    gist_response = await client.get(gist_url, headers=headers)
    gist_response.raise_for_status()
    document = read_jobs(gist_response.json())
    prune_jobs(document)

    trigger_id = job.get("trigger_id")
    if trigger_id:
        for existing in document["jobs"].values():
            if existing.get("trigger_id") == trigger_id:
                return int(existing.get("issue_number") or 0)

    document["jobs"][job["job_id"]] = job
    update_response = await client.patch(
        gist_url,
        headers=headers,
        json={"files": {JOB_FILE: {"content": json.dumps(document, ensure_ascii=False, indent=2)}}},
    )
    update_response.raise_for_status()

    issue_response = await client.post(
        f"{GITHUB_API}/repos/{repo}/issues",
        headers=headers,
        json={
            "title": f"{ISSUE_PREFIX} {job['job_id']}",
            "body": "Dooray 회의실 조회 작업입니다. 실제 요청 데이터는 비공개 Gist에 저장됩니다.",
        },
    )
    issue_response.raise_for_status()
    issue_number = int(issue_response.json()["number"])

    # 작업자가 첫 Gist PATCH 직후 처리를 시작할 수 있으므로 최신 문서를 다시 읽어
    # issue_number만 병합한다. 오래된 document로 작업 결과를 덮어쓰지 않는다.
    latest_response = await client.get(gist_url, headers=headers)
    latest_response.raise_for_status()
    latest_document = read_jobs(latest_response.json())
    latest_job = latest_document["jobs"].get(job["job_id"])
    if latest_job is None:
        latest_job = dict(job)
        latest_document["jobs"][job["job_id"]] = latest_job
    latest_job["issue_number"] = issue_number
    update_response = await client.patch(
        gist_url,
        headers=headers,
        json={"files": {JOB_FILE: {"content": json.dumps(latest_document, ensure_ascii=False, indent=2)}}},
    )
    update_response.raise_for_status()
    return issue_number


@router.post("/dooray/ai")
async def meeting_command(req: Request):
    github_token = os.environ.get("GITHUB_TOKEN", "")
    gist_id = os.environ.get("MEETING_GIST_ID", "")
    repo = os.environ.get("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    expected_app_token = os.environ.get("DOORAY_APP_TOKEN", "")
    if not all((github_token, gist_id, repo, expected_app_token)):
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
    if contains_mutation_request(query):
        return pack({
            "responseType": "ephemeral",
            "text": "회의실 봇에서는 조회만 지원합니다. 예약 신청·취소는 웹 화면을 이용해 주세요.",
        })

    response_url = str(data.get("responseUrl") or "")
    if not response_url.startswith("https://"):
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ Dooray 후속 응답 URL을 확인할 수 없습니다.",
        })

    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "status": "queued",
        "query": query,
        "response_url": response_url,
        "trigger_id": str(data.get("triggerId") or ""),
        "user_id": str(data.get("userId") or ""),
        "channel_id": str(data.get("channelId") or ""),
        "created_at": now.isoformat().replace("+00:00", "Z"),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            issue_number = await enqueue_job(client, github_token, gist_id, repo, job)
    except Exception as exc:
        return pack({
            "responseType": "ephemeral",
            "text": f"⚠️ 회의실 조회 요청을 등록하지 못했습니다: {type(exc).__name__}",
        })

    return pack({
        "responseType": "inChannel",
        "text": f"🔎 회의실 정보를 조회 중입니다. 완료되면 이 메시지를 결과로 바꾸겠습니다. (작업 #{issue_number})",
    })
