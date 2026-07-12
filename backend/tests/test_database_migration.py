import unittest

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from main import _migrate_add_columns


class DatabaseMigrationCase(unittest.IsolatedAsyncioTestCase):
    async def test_add_column_migration_is_idempotent(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text("CREATE TABLE agent_conversations (id VARCHAR(36) PRIMARY KEY)")
                )
                await _migrate_add_columns(conn)
                await _migrate_add_columns(conn)

                columns = await conn.run_sync(
                    lambda sync_conn: {
                        column["name"]
                        for column in sa.inspect(sync_conn).get_columns("agent_conversations")
                    }
                )
            self.assertIn("project_path", columns)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
