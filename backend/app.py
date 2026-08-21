import json
import os
import secrets
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite
import socketio
import uvicorn
from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .csv_io import export_csv, import_csv
from .database import DB_PATH, count_items, delete_item, get_audit_log, get_db, get_item_by_code, init_db, search_items, upsert_item
from .models import ItemCreate, ItemUpdate
from .qr import generate_qr


@asynccontextmanager
async def _get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
STATIC_DIR = os.path.join(FRONTEND_DIR, 'static')


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


HOST_PORT = int(os.environ.get('LAGER_PORT', '8000'))
HOST_IP = get_local_ip()
PROTOCOL = 'https' if (os.path.isfile(os.path.join(BASE_DIR, 'certs', 'cert.pem')) and os.path.isfile(os.path.join(BASE_DIR, 'certs', 'key.pem'))) else 'http'


class SessionManager:
    TOKEN_FILE = os.path.join(BASE_DIR, 'data', 'session_token.json')
    TOKEN_TTL_HOURS = 8

    def __init__(self) -> None:
        self.token = self._load_token()
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.host_sids: List[str] = []

    def _load_token(self) -> str:
        os.makedirs(os.path.dirname(self.TOKEN_FILE), exist_ok=True)
        try:
            with open(self.TOKEN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            token = data.get('token', '')
            created = datetime.fromisoformat(data.get('created_at', ''))
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            if token and age_hours < self.TOKEN_TTL_HOURS:
                return token
        except Exception:
            pass
        return self._generate_token()

    def _generate_token(self) -> str:
        token = secrets.token_urlsafe(8)
        try:
            with open(self.TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump({'token': token, 'created_at': datetime.now(timezone.utc).isoformat()}, f)
        except Exception:
            pass
        return token

    def regenerate(self) -> str:
        self.token = self._generate_token()
        return self.token

    def url(self) -> str:
        return f'{PROTOCOL}://{HOST_IP}:{HOST_PORT}/client?session={self.token}'


session_mgr = SessionManager()


sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title='Der Lagerist', lifespan=lifespan)
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


def host_file():
    return FileResponse(os.path.join(FRONTEND_DIR, 'host.html'))


def client_file():
    return FileResponse(os.path.join(FRONTEND_DIR, 'client.html'))


@app.get('/')
async def root():
    return host_file()


@app.get('/host')
@app.get('/host/')
async def host_page():
    return host_file()


@app.get('/client')
@app.get('/client/')
async def client_page():
    return client_file()


@app.get('/api/session')
async def get_session():
    return {
        'token': session_mgr.token,
        'url': session_mgr.url(),
        'host_ip': HOST_IP,
        'host_port': HOST_PORT,
        'protocol': PROTOCOL,
    }


@app.post('/api/session/regenerate')
async def regenerate_session():
    token = session_mgr.regenerate()
    payload = {'token': token, 'url': session_mgr.url(), 'host_ip': HOST_IP, 'host_port': HOST_PORT, 'protocol': PROTOCOL}
    await sio.emit('session:updated', payload)
    return payload


@app.get('/api/items')
async def list_items(search: Optional[str] = Query(None), skip: int = Query(0), limit: int = Query(100), db=Depends(get_db)):
    items = await search_items(db, search, skip, limit)
    total = await count_items(db, search)
    return {'items': items, 'total': total, 'skip': skip, 'limit': limit}


@app.get('/api/items/{code}')
async def read_item(code: str, db=Depends(get_db)):
    item = await get_item_by_code(db, code)
    if not item:
        return {'error': 'not_found'}, 404
    return item


async def _save_item_details(db, item_id: int, data: dict, changed_by: str = ''):
    from .database import upsert_laptop_details, add_rma
    details = {k: v for k, v in data.items() if k in ('t14_gen', 'owners', 'notes', 'sina_token')}
    if details:
        await upsert_laptop_details(db, item_id, details)
    if data.get('rma_date'):
        await add_rma(db, item_id, data['rma_date'], data.get('rma_description', ''))


CATEGORY_PREFIXES = {
    'laptop': 'LAP-',
    'netzteil': 'NTZ-',
    'peripherie': 'PER-',
    'sonstiges': 'LAG-',
}


def generate_code(category: str) -> str:
    prefix = CATEGORY_PREFIXES.get(category, 'LAG-')
    token = secrets.token_urlsafe(4).upper().replace('-', '').replace('_', '')
    return f'{prefix}{token}'


@app.post('/api/items')
async def create_item(item: ItemCreate, db=Depends(get_db)):
    data = item.model_dump(exclude_unset=True, exclude={'code'})
    code = item.code or generate_code(data.get('category', 'sonstiges'))
    result = await upsert_item(db, code, data, 'Host')
    if result and result.get('category') == 'laptop':
        await _save_item_details(db, result['id'], data)
        result = await get_item_by_code(db, code)
    await sio.emit('item:updated', result)
    return result


@app.put('/api/items/{code}')
async def update_item(code: str, item: ItemUpdate, db=Depends(get_db)):
    data = item.model_dump(exclude_unset=True)
    result = await upsert_item(db, code, data, 'Host')
    if result and result.get('category') == 'laptop':
        await _save_item_details(db, result['id'], data)
        result = await get_item_by_code(db, code)
    await sio.emit('item:updated', result)
    return result


@app.delete('/api/items/{code}')
async def remove_item(code: str, db=Depends(get_db)):
    ok = await delete_item(db, code)
    if not ok:
        return {'error': 'not_found'}, 404
    await sio.emit('item:deleted', {'code': code})
    return {'ok': True}


@app.get('/api/qr')
async def generic_qr(data: str, box_size: int = 10, border: int = 2):
    image = generate_qr(data, box_size=box_size, border=border)
    return Response(content=image, media_type='image/png')


@app.get('/api/items/{code}/qr')
async def item_qr(code: str, box_size: int = 10, border: int = 2, db=Depends(get_db)):
    item = await get_item_by_code(db, code)
    if not item:
        return {'error': 'not_found'}, 404
    data = item['code']
    image = generate_qr(data, box_size=box_size, border=border)
    return Response(content=image, media_type='image/png')


@app.get('/api/ca')
async def download_ca():
    ca_path = os.path.join(BASE_DIR, 'certs', 'rootCA.pem')
    if not os.path.isfile(ca_path):
        return {'error': 'not_found'}, 404
    return FileResponse(ca_path, media_type='application/x-x509-ca-cert', filename='rootCA.crt')


@app.get('/api/csv/export')
async def export_csv_endpoint(db=Depends(get_db)):
    items = await search_items(db)
    content = export_csv(items)
    return PlainTextResponse(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=lager.csv'},
    )


@app.post('/api/csv/import')
async def import_csv_endpoint(file: UploadFile = File(...), db=Depends(get_db)):
    raw = await file.read()
    text = raw.decode('utf-8-sig')
    imported = await import_csv(db, text)
    if imported:
        from .qr import generate_labels_pdf
        pdf = generate_labels_pdf(imported)
        pdf_path = os.path.join(BASE_DIR, 'data', 'etiketten.pdf')
        with open(pdf_path, 'wb') as f:
            f.write(pdf)
    await sio.emit('csv:imported', {'count': len(imported), 'labels_url': '/api/labels' if imported else None})
    return {'imported': len(imported), 'labels_url': '/api/labels' if imported else None}


@app.get('/api/labels')
async def download_labels():
    pdf_path = os.path.join(BASE_DIR, 'data', 'etiketten.pdf')
    if not os.path.isfile(pdf_path):
        return {'error': 'not_found'}, 404
    return FileResponse(pdf_path, media_type='application/pdf', filename='etiketten.pdf')


@app.get('/api/scans')
async def list_scans(db=Depends(get_db)):
    return await get_scans(db)


@app.get('/api/audit')
async def list_audit(item_code: Optional[str] = Query(None), db=Depends(get_db)):
    return await get_audit_log(db, item_code)


@sio.event
async def connect(sid, environ):
    print(f'connect {sid}')


@sio.event
async def disconnect(sid):
    print(f'disconnect {sid}')
    if sid in session_mgr.clients:
        del session_mgr.clients[sid]
    if sid in session_mgr.host_sids:
        session_mgr.host_sids.remove(sid)
    await sio.emit('clients:changed', list(session_mgr.clients.values()))


@sio.on('host:join')
async def host_join(sid, data=None):
    if sid not in session_mgr.host_sids:
        session_mgr.host_sids.append(sid)
    await sio.emit('session:updated', {'token': session_mgr.token, 'url': session_mgr.url()}, to=sid)
    await sio.emit('clients:changed', list(session_mgr.clients.values()), to=sid)


@sio.on('client:join')
async def client_join(sid, data):
    token = data.get('token', '') if data else ''
    name = data.get('name', 'Unbekannt') if data else 'Unbekannt'
    if token != session_mgr.token:
        await sio.emit('session:error', {'message': 'Ungültiger Session-Token.'}, to=sid)
        return
    session_mgr.clients[sid] = {'sid': sid, 'name': name, 'joined_at': datetime.now(timezone.utc).isoformat()}
    await sio.emit('client:joined', {'name': name}, to=sid)
    await sio.emit('clients:changed', list(session_mgr.clients.values()), skip_sid=sid)


@sio.on('client:scan')
async def client_scan(sid, data):
    code = data.get('code', '') if data else ''
    client_name = session_mgr.clients.get(sid, {}).get('name', 'Unbekannt') if sid in session_mgr.clients else 'Unbekannt'
    if sid in session_mgr.clients:
        session_mgr.clients[sid]['last_scan'] = code
    async with _get_db() as db:
        item = await get_item_by_code(db, code)
        await add_scan(db, code, client_name, session_mgr.token, item is not None)
    if item:
        await sio.emit('item:found', item, to=sid)
        await sio.emit('scan:result', {'sid': sid, 'code': code, 'found': True, 'item': item}, skip_sid=sid)
    else:
        await sio.emit('item:not_found', {'code': code}, to=sid)
        await sio.emit('scan:result', {'sid': sid, 'code': code, 'found': False}, skip_sid=sid)


@sio.on('client:update')
async def client_update(sid, data):
    code = data.get('code', '') if data else ''
    if not code:
        return
    client_name = session_mgr.clients.get(sid, {}).get('name', 'Unbekannt') if sid in session_mgr.clients else 'Unbekannt'
    update_data = {k: v for k, v in data.items() if k != 'code'}
    async with _get_db() as db:
        result = await upsert_item(db, code, update_data, client_name)
        if result and result.get('category') == 'laptop':
            await _save_item_details(db, result['id'], update_data, client_name)
            result = await get_item_by_code(db, code)
    if result:
        await sio.emit('item:updated', result)


@sio.on('host:update')
async def host_update(sid, data):
    code = data.get('code', '') if data else ''
    if not code:
        return
    update_data = {k: v for k, v in data.items() if k != 'code'}
    async with _get_db() as db:
        result = await upsert_item(db, code, update_data, 'Host')
        if result and result.get('category') == 'laptop':
            await _save_item_details(db, result['id'], update_data, 'Host')
            result = await get_item_by_code(db, code)
    if result:
        await sio.emit('item:updated', result)


@sio.on('host:delete')
async def host_delete(sid, data):
    code = data.get('code', '') if data else ''
    if not code:
        return
    async with _get_db() as db:
        await delete_item(db, code)
    await sio.emit('item:deleted', {'code': code})


if __name__ == '__main__':
    uvicorn.run('backend.app:asgi_app', host='0.0.0.0', port=HOST_PORT, reload=False)
