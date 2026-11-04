"""Supported launch path: listen on IPv4 loopback only."""
import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8005))
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, access_log=False, proxy_headers=False)

