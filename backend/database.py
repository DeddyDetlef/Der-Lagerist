import os
import aiosqlite
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'lager.db')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS laptop_details (
                item_id INTEGER PRIMARY KEY,
                t14_gen TEXT DEFAULT '',
                owners TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rmas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                rma_date TEXT NOT NULL,
                description TEXT DEFAULT '',
                FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                session_token TEXT DEFAULT '',
                found INTEGER DEFAULT 0,
                scanned_at TEXT NOT NULL
            )
        ''')
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def _get_laptop_details(db: aiosqlite.Connection, item_id: int) -> Optional[Dict[str, Any]]:
    async with db.execute('SELECT * FROM laptop_details WHERE item_id = ?', (item_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def _get_rmas(db: aiosqlite.Connection, item_id: int) -> List[Dict[str, Any]]:
    async with db.execute('SELECT * FROM rmas WHERE item_id = ? ORDER BY rma_date DESC', (item_id,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_item_by_code(db: aiosqlite.Connection, code: str) -> Optional[Dict[str, Any]]:
    async with db.execute('SELECT * FROM items WHERE code = ?', (code,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        item = dict(row)
        item_id = item['id']
        if item.get('category') == 'laptop':
            item['details'] = await _get_laptop_details(db, item_id)
        else:
            item['details'] = None
        item['rmas'] = await _get_rmas(db, item_id)
        return item


async def search_items(db: aiosqlite.Connection, search: Optional[str] = None) -> List[Dict[str, Any]]:
    if search:
        pattern = f'%{search}%'
        query = '''
            SELECT * FROM items
            WHERE code LIKE ? OR name LIKE ? OR location LIKE ? OR category LIKE ?
            ORDER BY updated_at DESC
        '''
        async with db.execute(query, (pattern, pattern, pattern, pattern)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    async with db.execute('SELECT * FROM items ORDER BY updated_at DESC') as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def upsert_item(db: aiosqlite.Connection, code: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = await get_item_by_code(db, code)
    if existing:
        fields = []
        values = []
        for key in ['name', 'category', 'description', 'location', 'quantity', 'unit']:
            if key in data:
                fields.append(f'{key} = ?')
                values.append(data[key])
        if fields:
            fields.append('updated_at = ?')
            values.append(_now())
            values.append(code)
            await db.execute(f'UPDATE items SET {", ".join(fields)} WHERE code = ?', values)
    else:
        await db.execute('''
            INSERT INTO items (code, name, category, description, location, quantity, unit, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            code,
            data.get('name', ''),
            data.get('category', 'sonstiges'),
            data.get('description', ''),
            data.get('location', ''),
            data.get('quantity', 0),
            data.get('unit', ''),
            _now(),
        ))
    await db.commit()
    item = await get_item_by_code(db, code)
    return item


async def upsert_laptop_details(db: aiosqlite.Connection, item_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = await _get_laptop_details(db, item_id)
    if existing:
        fields = []
        values = []
        for key in ['t14_gen', 'owners', 'notes']:
            if key in data:
                fields.append(f'{key} = ?')
                values.append(data[key])
        if fields:
            values.append(item_id)
            await db.execute(f'UPDATE laptop_details SET {", ".join(fields)} WHERE item_id = ?', values)
    else:
        await db.execute('''
            INSERT INTO laptop_details (item_id, t14_gen, owners, notes)
            VALUES (?, ?, ?, ?)
        ''', (
            item_id,
            data.get('t14_gen', ''),
            data.get('owners', ''),
            data.get('notes', ''),
        ))
    await db.commit()
    return await _get_laptop_details(db, item_id)


async def add_rma(db: aiosqlite.Connection, item_id: int, rma_date: str, description: str = '') -> Dict[str, Any]:
    await db.execute('INSERT INTO rmas (item_id, rma_date, description) VALUES (?, ?, ?)', (item_id, rma_date, description))
    await db.commit()
    return {'item_id': item_id, 'rma_date': rma_date, 'description': description}


async def add_scan(db: aiosqlite.Connection, code: str, client_name: str = '', session_token: str = '', found: bool = False) -> Dict[str, Any]:
    await db.execute(
        'INSERT INTO scans (code, client_name, session_token, found, scanned_at) VALUES (?, ?, ?, ?, ?)',
        (code, client_name, session_token, 1 if found else 0, _now())
    )
    await db.commit()
    return {'code': code, 'client_name': client_name, 'session_token': session_token, 'found': found}


async def get_scans(db: aiosqlite.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    async with db.execute('SELECT * FROM scans ORDER BY scanned_at DESC LIMIT ?', (limit,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_item(db: aiosqlite.Connection, code: str) -> bool:
    await db.execute('DELETE FROM items WHERE code = ?', (code,))
    await db.commit()
    return db.total_changes > 0
