import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import report_store
from report_store import ReportRecord
from routers import reports


def _created_at(*, days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class ReportRetentionCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(ReportRecord.__table__.create)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _add_record(self, report_id: str, created_at: str) -> None:
        async with self.sessions() as session:
            session.add(
                ReportRecord(
                    id=report_id,
                    type="inspect",
                    title="巡检",
                    created_at=created_at,
                    health_score=100,
                )
            )
            await session.commit()

    async def _record_exists(self, report_id: str) -> bool:
        async with self.sessions() as session:
            result = await session.execute(
                select(ReportRecord.id).where(ReportRecord.id == report_id)
            )
            return result.scalar_one_or_none() is not None

    async def test_expired_orphan_inspect_json_is_removed_and_public_route_is_404(self):
        report_id = "inspect_orphan_expired"
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            report_path = reports_dir / f"{report_id}.json"
            report_path.write_text(
                json.dumps(
                    {
                        "id": report_id,
                        "type": "inspect",
                        "created_at": _created_at(days_ago=91),
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(reports_dir, 90)

            self.assertEqual(deleted, 1)
            self.assertFalse(report_path.exists())
            with patch.object(reports, "REPORTS_DIR", reports_dir):
                with self.assertRaises(HTTPException) as missing:
                    await reports.public_inspect_report_pdf(report_id)

        self.assertEqual(missing.exception.status_code, 404)

    async def test_unlink_failure_keeps_expired_metadata_for_retry(self):
        report_id = "inspect_retry_unlink"
        created_at = _created_at(days_ago=91)
        await self._add_record(report_id, created_at)
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            report_path = reports_dir / f"{report_id}.json"
            report_path.write_text(
                json.dumps(
                    {"id": report_id, "type": "inspect", "created_at": created_at}
                ),
                encoding="utf-8",
            )
            real_unlink = Path.unlink

            def fail_target(path, *args, **kwargs):
                if path == report_path:
                    raise PermissionError("locked")
                return real_unlink(path, *args, **kwargs)

            with (
                patch.object(report_store, "AsyncSessionLocal", self.sessions),
                patch.object(Path, "unlink", fail_target),
            ):
                with self.assertLogs(report_store.logger, level="WARNING"):
                    deleted = await report_store.cleanup_old_reports(reports_dir, 90)

            self.assertEqual(deleted, 0)
            self.assertTrue(report_path.exists())
            self.assertTrue(await self._record_exists(report_id))

    async def test_fresh_malformed_mismatched_and_unsafe_entries_are_retained(self):
        unsafe_id = "../outside_report"
        await self._add_record(unsafe_id, _created_at(days_ago=91))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_dir = root / "reports"
            reports_dir.mkdir()
            outside = root / "outside_report.json"
            outside.write_text("outside", encoding="utf-8")
            fresh = reports_dir / "inspect_fresh.json"
            fresh.write_text(
                json.dumps(
                    {
                        "id": fresh.stem,
                        "type": "inspect",
                        "created_at": _created_at(days_ago=1),
                    }
                ),
                encoding="utf-8",
            )
            malformed = reports_dir / "inspect_malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            mismatched = reports_dir / "inspect_mismatched.json"
            mismatched.write_text(
                json.dumps(
                    {
                        "id": "different_id",
                        "type": "inspect",
                        "created_at": _created_at(days_ago=91),
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(reports_dir, 90)

            self.assertEqual(deleted, 0)
            self.assertTrue(fresh.exists())
            self.assertTrue(malformed.exists())
            self.assertTrue(mismatched.exists())
            self.assertTrue(outside.exists())
            self.assertTrue(await self._record_exists(unsafe_id))

    async def test_expired_metadata_does_not_delete_fresh_report_file(self):
        report_id = "inspect_fresh_with_old_meta"
        await self._add_record(report_id, _created_at(days_ago=91))
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp, f"{report_id}.json")
            report_path.write_text(
                json.dumps(
                    {
                        "id": report_id,
                        "type": "inspect",
                        "created_at": _created_at(days_ago=1),
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(Path(tmp), 90)

            self.assertEqual(deleted, 0)
            self.assertTrue(report_path.exists())
            self.assertTrue(await self._record_exists(report_id))

    async def test_expired_metadata_does_not_delete_malformed_report_file(self):
        report_id = "inspect_malformed_with_old_meta"
        await self._add_record(report_id, _created_at(days_ago=91))
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp, f"{report_id}.json")
            report_path.write_text("{not-json", encoding="utf-8")
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(Path(tmp), 90)

            self.assertEqual(deleted, 0)
            self.assertTrue(report_path.exists())
            self.assertTrue(await self._record_exists(report_id))

    async def test_expired_metadata_does_not_delete_id_mismatched_report_file(self):
        report_id = "inspect_mismatch_with_old_meta"
        await self._add_record(report_id, _created_at(days_ago=91))
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp, f"{report_id}.json")
            report_path.write_text(
                json.dumps(
                    {
                        "id": "inspect_different",
                        "type": "inspect",
                        "created_at": _created_at(days_ago=91),
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(Path(tmp), 90)

            self.assertEqual(deleted, 0)
            self.assertTrue(report_path.exists())
            self.assertTrue(await self._record_exists(report_id))

    async def test_expired_metadata_without_report_file_is_removed(self):
        report_id = "inspect_missing_with_old_meta"
        await self._add_record(report_id, _created_at(days_ago=91))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(Path(tmp), 90)

            self.assertEqual(deleted, 0)
            self.assertFalse(await self._record_exists(report_id))

    async def test_validated_expired_file_is_deleted_before_its_metadata(self):
        report_id = "inspect_validated_expired"
        created_at = _created_at(days_ago=91)
        await self._add_record(report_id, created_at)
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp, f"{report_id}.json")
            report_path.write_text(
                json.dumps(
                    {"id": report_id, "type": "inspect", "created_at": created_at}
                ),
                encoding="utf-8",
            )
            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(Path(tmp), 90)

            self.assertEqual(deleted, 1)
            self.assertFalse(report_path.exists())
            self.assertFalse(await self._record_exists(report_id))

    async def test_pathological_timezone_does_not_block_later_expired_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            pathological = reports_dir / "inspect_pathological.json"
            pathological.write_text(
                json.dumps(
                    {
                        "id": pathological.stem,
                        "type": "inspect",
                        "created_at": "0001-01-01T00:00:00+23:59",
                    }
                ),
                encoding="utf-8",
            )
            expired = reports_dir / "inspect_valid_after_pathological.json"
            expired.write_text(
                json.dumps(
                    {
                        "id": expired.stem,
                        "type": "inspect",
                        "created_at": _created_at(days_ago=91),
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(report_store, "AsyncSessionLocal", self.sessions):
                deleted = await report_store.cleanup_old_reports(reports_dir, 90)

            self.assertEqual(deleted, 1)
            self.assertTrue(pathological.exists())
            self.assertFalse(expired.exists())


if __name__ == "__main__":
    unittest.main()
