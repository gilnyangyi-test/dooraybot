import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from api.meeting import contains_mutation_request, normalize_query, router
from worker.meeting_worker import extract_job_id, format_result, process_issue


app = FastAPI()
app.include_router(router)


class MeetingApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "test-token",
                "MEETING_GIST_ID": "test-meeting-gist",
                "GITHUB_REPO": "owner/repo",
                "DOORAY_APP_TOKEN": "dooray-secret",
            },
            clear=False,
        )
        self.env.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.env.stop()

    async def test_valid_query_creates_queue_job(self):
        with patch("api.meeting.enqueue_job", new=AsyncMock(return_value=42)) as enqueue:
            response = await self.client.post(
                "/dooray/meeting",
                json={
                    "appToken": "dooray-secret",
                    "text": '/meeting "10월 1일 예약 현황을 알려줘"',
                    "responseUrl": "https://dooray.example/hook/id",
                    "triggerId": "trigger-1",
                    "userId": "user-1",
                    "channelId": "channel-1",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("작업 #42", response.json()["text"])
        job = enqueue.await_args.args[-1]
        self.assertEqual(job["query"], "10월 1일 예약 현황을 알려줘")
        self.assertEqual(job["status"], "queued")

    async def test_invalid_app_token_is_rejected(self):
        response = await self.client.post(
            "/dooray/meeting",
            json={"appToken": "wrong", "text": "10월 1일 예약 현황"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("유효하지 않은", response.json()["text"])

    async def test_mutation_request_is_rejected(self):
        response = await self.client.post(
            "/dooray/meeting",
            json={
                "appToken": "dooray-secret",
                "text": "10월 1일 1동 283호 예약 취소해줘",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("조회만 지원", response.json()["text"])


class HelperTests(unittest.TestCase):
    def test_normalize_query(self):
        self.assertEqual(
            normalize_query('/meeting "10월 1일 예약 현황을 알려줘"'),
            "10월 1일 예약 현황을 알려줘",
        )
        self.assertEqual(
            normalize_query('/ai "10월 1일 예약 현황을 알려줘"'),
            "10월 1일 예약 현황을 알려줘",
        )

    def test_mutation_detection_does_not_block_schedule_query(self):
        self.assertFalse(contains_mutation_request("10월 1일 예약 현황을 알려줘"))
        self.assertTrue(contains_mutation_request("10월 1일 예약 취소해줘"))

    def test_worker_job_id_and_format(self):
        job_id = "a" * 32
        self.assertEqual(
            extract_job_id({"title": f"[meeting-job] {job_id}"}), job_id
        )
        text = format_result(
            {
                "answer": "2026-10-01 예약 현황",
                "cards": [
                    {
                        "name": "1동 283호 회의실",
                        "status": "reserved",
                        "bookings": ["12:00 ~ 13:00 회의실 테스트"],
                    }
                ],
            }
        )
        self.assertIn("1동 283호 회의실 · 예약 있음", text)
        self.assertIn("회의실 테스트", text)

    def test_worker_processes_job_and_closes_issue(self):
        job_id = "b" * 32

        class FakeQueue:
            def __init__(self):
                self.job = {
                    "status": "queued",
                    "query": "10월 1일 예약 현황",
                    "response_url": "https://dooray.example/hook/id",
                }
                self.updates = []
                self.closed = []

            def jobs_document(self):
                return {"jobs": {job_id: self.job}}

            def update_job(self, _job_id, **changes):
                self.job.update(changes)
                self.updates.append(changes)
                return self.job

            def close_issue(self, issue_number):
                self.closed.append(issue_number)

        queue = FakeQueue()
        issue = {"number": 7, "title": f"[meeting-job] {job_id}"}
        with patch(
            "worker.meeting_worker.run_meeting_query",
            return_value={"answer": "조회 완료", "cards": []},
        ), patch("worker.meeting_worker.send_dooray_result") as send:
            self.assertTrue(process_issue(queue, issue))
        self.assertEqual(queue.job["status"], "completed")
        self.assertEqual(queue.closed, [7])
        send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
