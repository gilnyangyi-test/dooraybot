"""GitHub Issue를 감지해 개인 PC의 회의실 조회 API를 실행하는 작업자."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
GITHUB_API = "https://api.github.com"
JOB_FILE = "meeting_jobs.json"
ISSUE_PREFIX = "[meeting-job]"
DEFAULT_GITHUB_REPO = "gilnyangyi-test/dooraybot"


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env(BASE_DIR / ".env.worker")


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} 환경변수가 필요합니다.")
    return value


class GitHubQueue:
    def __init__(self) -> None:
        self.token = required_env("GITHUB_TOKEN")
        self.gist_id = required_env("MEETING_GIST_ID")
        self.repo = os.environ.get("GITHUB_REPO", DEFAULT_GITHUB_REPO).strip()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, url, timeout=20, **kwargs)
        response.raise_for_status()
        return response

    def open_issues(self) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"{GITHUB_API}/repos/{self.repo}/issues",
            params={"state": "open", "per_page": 50, "sort": "created", "direction": "asc"},
        )
        return [
            issue for issue in response.json()
            if "pull_request" not in issue
            and str(issue.get("title", "")).startswith(ISSUE_PREFIX)
        ]

    def jobs_document(self) -> dict[str, Any]:
        response = self._request("GET", f"{GITHUB_API}/gists/{self.gist_id}")
        file_data = response.json().get("files", {}).get(JOB_FILE)
        if not file_data:
            return {"version": 1, "jobs": {}}
        document = json.loads(file_data.get("content") or "{}")
        if not isinstance(document.get("jobs"), dict):
            document["jobs"] = {}
        return document

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        document = self.jobs_document()
        job = document.get("jobs", {}).get(job_id)
        if not job:
            raise RuntimeError(f"Gist에서 작업 {job_id}을 찾지 못했습니다.")
        job.update(changes)
        self._request(
            "PATCH",
            f"{GITHUB_API}/gists/{self.gist_id}",
            json={"files": {JOB_FILE: {"content": json.dumps(document, ensure_ascii=False, indent=2)}}},
        )
        return job

    def close_issue(self, issue_number: int) -> None:
        self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}",
            json={"state": "closed", "state_reason": "completed"},
        )


def extract_job_id(issue: dict[str, Any]) -> str | None:
    match = re.fullmatch(rf"{re.escape(ISSUE_PREFIX)}\s+([0-9a-f]{{32}})", str(issue.get("title", "")))
    return match.group(1) if match else None


def format_result(data: dict[str, Any]) -> str:
    lines = [str(data.get("answer") or "조회 결과가 없습니다.").strip()]
    status_labels = {
        "available": "예약 가능",
        "partial": "일부 예약",
        "reserved": "예약 있음",
        "error": "확인 실패",
    }
    for card in data.get("cards") or []:
        name = card.get("name") or card.get("room") or "회의실"
        status = status_labels.get(str(card.get("status")), str(card.get("status") or ""))
        lines.append(f"\n- {name} · {status}")
        bookings = card.get("bookings") or []
        for item in bookings[:5]:
            lines.append(f"  - {item}")
        free_dates = card.get("free_dates") or []
        if free_dates and not bookings:
            lines.append("  - " + ", ".join(map(str, free_dates[:15])))
    text = "\n".join(lines).strip()
    return text[:7000]


def send_dooray_result(response_url: str, text: str) -> None:
    if not response_url.startswith("https://"):
        raise RuntimeError("Dooray responseUrl이 올바르지 않습니다.")
    response = requests.post(
        response_url,
        json={"responseType": "inChannel", "replaceOriginal": False, "text": text},
        timeout=20,
    )
    response.raise_for_status()


def run_meeting_query(query: str) -> dict[str, Any]:
    api_url = required_env("MEETING_API_URL")
    response = requests.post(
        api_url,
        json={"message": query, "show_browser": False},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("intent") == "reservation_action":
        raise RuntimeError("Dooray에서는 예약 신청·취소를 지원하지 않습니다.")
    return data


def process_issue(queue: GitHubQueue, issue: dict[str, Any], dry_run: bool = False) -> bool:
    job_id = extract_job_id(issue)
    if not job_id:
        return False
    document = queue.jobs_document()
    job = document.get("jobs", {}).get(job_id)
    if not job or job.get("status") not in {"queued", "processing"}:
        return False
    issue_number = int(issue["number"])
    print(f"[meeting-worker] 작업 #{issue_number} 처리 시작 ({job_id[:8]})")
    if dry_run:
        print(f"[meeting-worker] DRY RUN 질의: {job.get('query', '')}")
        return True

    queue.update_job(job_id, status="processing", started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    try:
        result = run_meeting_query(str(job.get("query") or ""))
        message = format_result(result)
        send_dooray_result(str(job.get("response_url") or ""), message)
        queue.update_job(
            job_id,
            status="completed",
            result=message,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        print(f"[meeting-worker] 작업 #{issue_number} 완료")
    except Exception as exc:
        error_message = f"⚠️ 회의실 조회에 실패했습니다: {type(exc).__name__}: {exc}"
        try:
            send_dooray_result(str(job.get("response_url") or ""), error_message)
        except Exception:
            pass
        queue.update_job(
            job_id,
            status="failed",
            error=error_message,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        print(error_message, file=sys.stderr)
    finally:
        queue.close_issue(issue_number)
    return True


def run_once(queue: GitHubQueue, dry_run: bool = False) -> int:
    processed = 0
    for issue in queue.open_issues():
        if process_issue(queue, issue, dry_run=dry_run):
            processed += 1
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Dooray 회의실 GitHub Issue 작업자")
    parser.add_argument("--once", action="store_true", help="한 번 확인 후 종료")
    parser.add_argument("--dry-run", action="store_true", help="작업을 실행하거나 완료 처리하지 않음")
    args = parser.parse_args()
    queue = GitHubQueue()
    interval = max(5, int(os.environ.get("MEETING_POLL_SECONDS", "15")))
    if args.once:
        print(f"[meeting-worker] 처리 대상 {run_once(queue, args.dry_run)}건")
        return 0
    print(f"[meeting-worker] {interval}초 간격으로 GitHub Issue를 확인합니다.")
    while True:
        try:
            run_once(queue, args.dry_run)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"[meeting-worker] 폴링 오류: {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
