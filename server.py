import os
import shutil
import socket
import subprocess
import sys

# Import backend to ensure PyInstaller bundles all dependencies
import backend.app  # noqa: F401


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


def find_free_port(start=8000, end=9000):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('0.0.0.0', port)) != 0:
                return port
    return start


def find_openssl():
    candidates = [
        r'C:\Program Files\Git\usr\bin\openssl.exe',
        r'C:\Program Files\Git\mingw64\bin\openssl.exe',
        r'C:\ProgramData\chocolatey\bin\openssl.exe',
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    openssl = shutil.which('openssl')
    if openssl:
        return openssl
    return None


def find_mkcert():
    return shutil.which('mkcert')


def generate_mkcert_certs(certs_dir, ip):
    key_file = os.path.join(certs_dir, 'key.pem')
    cert_file = os.path.join(certs_dir, 'cert.pem')
    mkcert = find_mkcert()
    if not mkcert:
        return False
    try:
        subprocess.run([mkcert, '-install'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run([mkcert, '-key-file', key_file, '-cert-file', cert_file, ip, '127.0.0.1', 'localhost'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        print(f'mkcert fehlgeschlagen: {e}', file=sys.stderr)
        return False


def generate_openssl_certs(certs_dir, ip):
    key_file = os.path.join(certs_dir, 'key.pem')
    cert_file = os.path.join(certs_dir, 'cert.pem')
    openssl = find_openssl()
    if not openssl:
        return False
    try:
        subprocess.run([
            openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', key_file,
            '-out', cert_file, '-days', '365', '-nodes',
            '-subj', f'/CN={ip}', '-addext', f'subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost'
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        print(f'OpenSSL fehlgeschlagen: {e}', file=sys.stderr)
        return False


def ensure_certs(certs_dir, ip):
    key_file = os.path.join(certs_dir, 'key.pem')
    cert_file = os.path.join(certs_dir, 'cert.pem')
    if os.path.isfile(key_file) and os.path.isfile(cert_file):
        return cert_file, key_file
    os.makedirs(certs_dir, exist_ok=True)
    if generate_mkcert_certs(certs_dir, ip):
        return cert_file, key_file
    if generate_openssl_certs(certs_dir, ip):
        return cert_file, key_file
    return None, None


def main():
    import uvicorn

    base_dir = get_base_dir()
    os.chdir(base_dir)
    os.environ['LAGER_BASE_DIR'] = base_dir

    data_dir = os.path.join(base_dir, 'data')
    certs_dir = os.path.join(base_dir, 'certs')
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(certs_dir, exist_ok=True)

    ip = get_local_ip()
    port_env = os.environ.get('LAGER_PORT')
    if port_env:
        port = int(port_env)
    else:
        port = find_free_port()

    cert_file, key_file = ensure_certs(certs_dir, ip)

    print(f'====================================================')
    print(f'  Der Lagerist wird gestartet')
    print(f'  Host-URL: https://{ip}:{port}/host')
    print(f'  Client-URL: https://{ip}:{port}/client')
    print(f'====================================================')

    if cert_file and key_file:
        uvicorn.run('backend.app:asgi_app', host='0.0.0.0', port=port, ssl_keyfile=key_file, ssl_certfile=cert_file)
    else:
        print('Warnung: Keine Zertifikate gefunden/erstellt. Starte HTTP.', file=sys.stderr)
        uvicorn.run('backend.app:asgi_app', host='0.0.0.0', port=port)


if __name__ == '__main__':
    main()
