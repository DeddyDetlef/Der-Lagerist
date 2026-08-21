import asyncio
import os
import tempfile
import unittest
import aiosqlite
from backend.database import (
    init_db,
    get_item_by_code,
    upsert_item,
    upsert_laptop_details,
    add_rma,
    add_audit_log,
    get_audit_log,
    add_scan,
    get_scans,
)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

    async def asyncTearDown(self):
        await self.db.close()
        os.unlink(self.db_path)

    async def _init_schema(self):
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                category TEXT DEFAULT 'sonstiges',
                description TEXT DEFAULT '',
                location TEXT DEFAULT '',
                quantity REAL DEFAULT 0,
                unit TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS laptop_details (
                item_id INTEGER PRIMARY KEY,
                t14_gen TEXT DEFAULT '',
                owners TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                sina_token TEXT DEFAULT '',
                FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS rmas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                rma_date TEXT NOT NULL,
                description TEXT DEFAULT '',
                FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                session_token TEXT DEFAULT '',
                found INTEGER DEFAULT 0,
                scanned_at TEXT NOT NULL
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_code TEXT NOT NULL,
                action TEXT NOT NULL,
                changes TEXT DEFAULT '',
                changed_by TEXT DEFAULT '',
                changed_at TEXT NOT NULL
            )
        ''')
        await self.db.commit()

    async def test_upsert_and_get_item(self):
        await self._init_schema()
        item = await upsert_item(self.db, 'LAG-001', {'name': 'Schrauben', 'quantity': 100})
        self.assertIsNotNone(item)
        self.assertEqual(item['code'], 'LAG-001')

        found = await get_item_by_code(self.db, 'LAG-001')
        self.assertEqual(found['name'], 'Schrauben')

    async def test_laptop_details(self):
        await self._init_schema()
        item = await upsert_item(self.db, 'LAP-001', {'name': 'T14', 'category': 'laptop'})
        details = await upsert_laptop_details(self.db, item['id'], {'t14_gen': 'gen3', 'sina_token': 'token123'})
        self.assertEqual(details['t14_gen'], 'gen3')

    async def test_rma(self):
        await self._init_schema()
        item = await upsert_item(self.db, 'LAP-002', {'name': 'T14 Gen 1', 'category': 'laptop'})
        rma = await add_rma(self.db, item['id'], '2025-01-15', 'Display')
        self.assertEqual(rma['description'], 'Display')

    async def test_audit_log(self):
        await self._init_schema()
        await upsert_item(self.db, 'LAG-002', {'name': 'Test'}, 'Host')
        log = await get_audit_log(self.db, 'LAG-002')
        self.assertTrue(len(log) > 0)
        self.assertEqual(log[0]['action'], 'create')

    async def test_scans(self):
        await self._init_schema()
        await add_scan(self.db, 'LAG-001', 'Max', 'token', True)
        scans = await get_scans(self.db)
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]['found'], 1)


if __name__ == '__main__':
    unittest.main()
