import asyncio
import json
import os
import sys
import time
import urllib.request
import urllib.error

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'lager.db')

HOST = 'https://127.0.0.1:8000'


def api_get(path):
    try:
        ctx = urllib.request.ssl._create_unverified_context()
        with urllib.request.urlopen(f'{HOST}{path}', context=ctx, timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def db_query(query, params=()):
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def make_session_panel():
    data = api_get('/api/session')
    if not data:
        return Panel('Server nicht erreichbar', title='Session', border_style='red')
    text = Text()
    text.append(f"Token: {data.get('token', '-')}\n")
    text.append(f"Client-URL: {data.get('url', '-')}")
    return Panel(text, title='Session', border_style='green')


def make_clients_panel():
    return Panel('Clients werden über Socket.IO erfasst...', title='Verbundene Clients', border_style='blue')


def make_scans_panel():
    scans = db_query('SELECT * FROM scans ORDER BY scanned_at DESC LIMIT 8')
    if not scans:
        return Panel('Keine Scans', title='Letzte Scans', border_style='yellow')
    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Zeit')
    table.add_column('Code')
    table.add_column('Client')
    table.add_column('Status')
    for s in scans:
        status = 'gefunden' if s.get('found') else 'nicht gefunden'
        table.add_row(s.get('scanned_at', '')[:19], s.get('code', ''), s.get('client_name', ''), status)
    return Panel(table, title='Letzte Scans', border_style='yellow')


def make_stock_panel():
    data = api_get('/api/items?limit=20')
    if not data or not data.get('items'):
        return Panel('Keine Objekte', title='Lagerbestand', border_style='cyan')
    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Name')
    table.add_column('Sina Token')
    table.add_column('Kategorie')
    table.add_column('Ort')
    table.add_column('Zustand')
    for item in data.get('items', []):
        zustand = item.get('unit', '') if item.get('category') == 'laptop' else f"{item.get('quantity', '')} {item.get('unit', '')}"
        table.add_row(
            item.get('name', ''),
            item.get('sina_token', '') if item.get('category') == 'laptop' else '-',
            item.get('category', ''),
            item.get('location', ''),
            zustand,
        )
    return Panel(table, title='Lagerbestand', border_style='cyan')


def update_ui():
    layout = Layout()
    layout.split_column(
        Layout(name='top', size=5),
        Layout(name='main'),
    )
    layout['top'].split_row(
        Layout(make_session_panel()),
        Layout(make_clients_panel()),
    )
    layout['main'].split_row(
        Layout(make_scans_panel(), ratio=1),
        Layout(make_stock_panel(), ratio=2),
    )
    return layout


async def main():
    console.print('Der Lagerist - Text-UI', style='bold green')
    console.print(f'Server: {HOST}', style='dim')
    console.print('Beenden mit Strg+C\n')
    try:
        with Live(update_ui(), refresh_per_second=2, screen=False) as live:
            while True:
                live.update(update_ui())
                await asyncio.sleep(2)
    except KeyboardInterrupt:
        console.print('\nBeendet.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        console.print(f'Fehler: {e}', style='red')
