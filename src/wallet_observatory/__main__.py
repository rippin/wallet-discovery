import argparse
import math
from dataclasses import replace
import signal
import threading

from .config import Config
from .db import Store
from .collector import Collector
from .server import make_server

def main():
    parser=argparse.ArgumentParser(description='Read-only wallet research dashboard')
    parser.add_argument('--demo',action='store_true',help='Synthetic data, isolated database, no network collection')
    parser.add_argument('--once',action='store_true',help='Run one collection cycle and exit')
    parser.add_argument('--db')
    parser.add_argument('--port',type=int)
    args=parser.parse_args(); cfg=Config.env()
    if args.db: cfg.db=args.db
    if args.port: cfg.port=args.port
    if args.demo:
        cfg=replace(cfg,live=False,db=args.db or 'data/demo.sqlite3')
    if not math.isfinite(cfg.min_market_cap):
        parser.error('OBS_MIN_MARKET_CAP_USD must be finite')
    if cfg.monthly_credits<=0 or cfg.rpc_credit_cost<=0:
        parser.error('Credit settings must be positive')
    if cfg.host not in ('127.0.0.1','localhost','::1') and len(cfg.password)<7:
        parser.error('Non-loopback serving requires OBS_PASSWORD of at least 7 characters and a TLS proxy')
    if cfg.live and not cfg.rpc_url:
        parser.error('Live collection requires HELIUS_API_KEY or OBS_RPC_URL')
    store=Store(cfg.db)
    mode='demo' if args.demo else 'live'
    previous=store.meta('mode')
    if previous and previous!=mode:
        parser.error('Demo and live data must use separate databases')
    store.meta('mode',mode)
    if args.demo:
        from .demo import seed
        seed(store)
    collector=Collector(store,cfg)
    if args.once:
        if not cfg.live: parser.error('--once requires OBS_LIVE=1')
        collector.cycle(); return
    if cfg.live:
        threading.Thread(target=collector.run,daemon=True).start()
    server=make_server(store,cfg)
    def stop(*_):
        collector.stop.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    print(f'Wallet Observatory: http://{cfg.host}:{cfg.port} | {mode} | collector {"on" if cfg.live else "off"}',flush=True)
    try: server.serve_forever()
    finally: collector.stop.set(); server.server_close()

if __name__=='__main__': main()
