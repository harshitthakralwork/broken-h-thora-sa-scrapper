"""One-shot worker. A watchdog also terminates it if its parent disappears."""
import json
import os
import sys
import threading
import time

def main():
    try:
        payload=json.loads(sys.stdin.read(16_384))
        seconds=float(payload['deadline_seconds'])
        if seconds<=0 or seconds>60: raise ValueError('Invalid deadline')
        url=payload['url']
        if not isinstance(url,str) or len(url)>2048: raise ValueError('Invalid URL')
    except (ValueError,KeyError,TypeError):
        print(json.dumps({'ok':False,'code':'invalid'})); return
    watchdog=threading.Timer(seconds,lambda:os._exit(124));watchdog.daemon=True;watchdog.start()
    try:
        from crawler import Coordinator,fetch_public_page,CrawlBusy,CrawlDeadline,CrawlBlocked
        deadline=time.monotonic()+seconds
        coordinator=Coordinator(os.environ['DATABASE_URL'])
        try:
            with coordinator.lease(seconds):
                final_url,html=fetch_public_page(url,coordinator,deadline)
                output={'ok':True,'url':final_url,'html':html}
        finally: coordinator.close()
    except CrawlBusy: output={'ok':False,'code':'busy'}
    except CrawlDeadline: output={'ok':False,'code':'deadline'}
    except CrawlBlocked: output={'ok':False,'code':'blocked'}
    except Exception: output={'ok':False,'code':'failure'}
    try: print(json.dumps(output,ensure_ascii=True),flush=True)
    finally: watchdog.cancel()

if __name__=='__main__': main()
