import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS token_openings(wallet TEXT NOT NULL,mint TEXT NOT NULL,chain_time REAL NOT NULL,quantity REAL NOT NULL,PRIMARY KEY(wallet,mint));
CREATE TABLE IF NOT EXISTS token_flows(signature TEXT NOT NULL,wallet TEXT NOT NULL,mint TEXT NOT NULL,chain_time REAL NOT NULL,delta REAL NOT NULL,PRIMARY KEY(signature,wallet,mint));
CREATE INDEX IF NOT EXISTS token_flows_wallet_time ON token_flows(wallet,chain_time);
CREATE TABLE IF NOT EXISTS quote_budget(day TEXT PRIMARY KEY,requests INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS focus_queue(wallet TEXT NOT NULL,signature TEXT NOT NULL,chain_time REAL,attempts INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(wallet,signature));
CREATE TABLE IF NOT EXISTS focus_state(wallet TEXT PRIMARY KEY,cursor TEXT,next_scan REAL NOT NULL DEFAULT 0,last_poll REAL,gaps INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS research_runs(id INTEGER PRIMARY KEY,started_at REAL NOT NULL,ends_at REAL NOT NULL,rules TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_members(run_id INTEGER NOT NULL,wallet TEXT NOT NULL,reason TEXT NOT NULL,prior TEXT NOT NULL,PRIMARY KEY(run_id,wallet));
CREATE TABLE IF NOT EXISTS research_samples(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL,signal_id INTEGER NOT NULL UNIQUE,
 wallet TEXT NOT NULL,mint TEXT NOT NULL,arm TEXT NOT NULL,detected_at REAL NOT NULL,market_cap REAL,liquidity REAL,token_age REAL,
 UNIQUE(run_id,wallet,mint));
CREATE TABLE IF NOT EXISTS research_results(sample_id INTEGER NOT NULL,delay INTEGER NOT NULL,horizon INTEGER NOT NULL,
 status TEXT NOT NULL,entry_at REAL,exit_at REAL,return_pct REAL,worst_return REAL,best_return REAL,
 profitable_seconds REAL,path_samples INTEGER NOT NULL DEFAULT 0,max_gap REAL,entry_disadvantage REAL,sold_before_entry REAL,
 PRIMARY KEY(sample_id,delay,horizon));
CREATE TABLE IF NOT EXISTS route_checks(id INTEGER PRIMARY KEY,mint TEXT NOT NULL,at REAL NOT NULL,size_usdc REAL NOT NULL,
 status TEXT NOT NULL,roundtrip_usdc REAL,buy_impact REAL,sell_impact REAL,router TEXT);
CREATE INDEX IF NOT EXISTS route_checks_mint_time ON route_checks(mint,at);
CREATE INDEX IF NOT EXISTS research_samples_time ON research_samples(detected_at);

CREATE TABLE IF NOT EXISTS trade_values(trade_id INTEGER PRIMARY KEY,usd_amount REAL NOT NULL,price_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS quote_prices(mint TEXT PRIMARY KEY,price REAL,observed_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS admission_values(signature TEXT NOT NULL,wallet TEXT NOT NULL,mint TEXT NOT NULL,
 quote_mint TEXT,quote_quantity REAL,estimated_usd REAL,valued_at REAL,
 PRIMARY KEY(signature,wallet,mint));

CREATE TABLE IF NOT EXISTS discovery_windows(id INTEGER PRIMARY KEY,program TEXT NOT NULL,started_at REAL NOT NULL,
 completed_at REAL,head TEXT,before_signature TEXT,previous_cursor TEXT,state TEXT NOT NULL DEFAULT 'enumerating',
 pages INTEGER NOT NULL DEFAULT 0,available INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,
 skipped INTEGER NOT NULL DEFAULT 0,inspected INTEGER NOT NULL DEFAULT 0,unavailable INTEGER NOT NULL DEFAULT 0,
 ambiguous INTEGER NOT NULL DEFAULT 0,unsupported INTEGER NOT NULL DEFAULT 0,gap INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS discovery_queue(program TEXT NOT NULL,signature TEXT NOT NULL,window_id INTEGER NOT NULL,
 chain_time REAL,sequence INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(program,signature));
CREATE INDEX IF NOT EXISTS discovery_pending ON discovery_queue(status,window_id,sequence);
CREATE INDEX IF NOT EXISTS discovery_fresh ON discovery_queue(status,program,chain_time DESC,window_id DESC,sequence);
CREATE TABLE IF NOT EXISTS discovery_buyers(window_id INTEGER NOT NULL,wallet TEXT NOT NULL,PRIMARY KEY(window_id,wallet));
CREATE TABLE IF NOT EXISTS admission_pending(signature TEXT NOT NULL,wallet TEXT NOT NULL,mint TEXT NOT NULL,
 observed_at REAL NOT NULL,PRIMARY KEY(signature,wallet,mint));

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wallets(address TEXT PRIMARY KEY,first_seen REAL NOT NULL,last_seen REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'candidate',next_scan REAL NOT NULL DEFAULT 0,last_scan REAL,
 cursor TEXT,reason TEXT NOT NULL DEFAULT 'Awaiting prospective evidence');
CREATE TABLE IF NOT EXISTS tokens(mint TEXT PRIMARY KEY,symbol TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,
 platform TEXT,first_seen REAL NOT NULL,last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS transactions(signature TEXT PRIMARY KEY,chain_time REAL,observed_at REAL NOT NULL,
 raw TEXT NOT NULL,parse_status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,signature TEXT NOT NULL,wallet TEXT NOT NULL,mint TEXT NOT NULL,
 side TEXT NOT NULL,quantity REAL NOT NULL,quote_mint TEXT,quote_quantity REAL,chain_time REAL NOT NULL,
 observed_at REAL NOT NULL,venue TEXT NOT NULL,platform TEXT,quality TEXT NOT NULL,
 UNIQUE(signature,wallet,mint));
CREATE INDEX IF NOT EXISTS trades_wallet_time ON trades(wallet,chain_time);
CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY,source TEXT NOT NULL,target TEXT NOT NULL,
 signature TEXT NOT NULL,observed_at REAL NOT NULL,kind TEXT NOT NULL,amount REAL,
 UNIQUE(source,target,signature,kind));
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,mint TEXT NOT NULL,observed_at REAL NOT NULL,
 price REAL,liquidity REAL,volume REAL,pair TEXT,status TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS snapshots_mint_time ON snapshots(mint,observed_at);
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY,trade_id INTEGER UNIQUE NOT NULL,wallet TEXT NOT NULL,
 mint TEXT NOT NULL,detected_at REAL NOT NULL,eligible INTEGER NOT NULL DEFAULT 1,read INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outcomes(signal_id INTEGER NOT NULL,delay INTEGER NOT NULL,horizon INTEGER NOT NULL,
 entry_at REAL,exit_at REAL,entry_price REAL,exit_price REAL,return_pct REAL,status TEXT NOT NULL,
 PRIMARY KEY(signal_id,delay,horizon));
CREATE TABLE IF NOT EXISTS paper(id INTEGER PRIMARY KEY,mint TEXT NOT NULL,opened_at REAL NOT NULL,
 entry_price REAL NOT NULL,invested REAL NOT NULL,quantity REAL NOT NULL,remaining REAL NOT NULL,
 realized REAL NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',signal_id INTEGER,model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_exits(id INTEGER PRIMARY KEY,position_id INTEGER NOT NULL,closed_at REAL NOT NULL,
 quantity REAL NOT NULL,price REAL NOT NULL,proceeds REAL NOT NULL,pnl REAL NOT NULL,notes TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budgets(day TEXT NOT NULL,bucket TEXT NOT NULL,credits INTEGER NOT NULL,
 PRIMARY KEY(day,bucket));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,kind TEXT NOT NULL,message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY,wallet TEXT NOT NULL,at REAL NOT NULL,
 status TEXT NOT NULL,reason TEXT NOT NULL,samples INTEGER NOT NULL,median_return REAL);
'''

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            # Additive migration: keep old eligibility and outcome records unchanged.
            columns={row['name'] for row in db.execute('PRAGMA table_info(signals)')}
            if 'observation_class' not in columns:
                db.execute("ALTER TABLE signals ADD COLUMN observation_class TEXT NOT NULL DEFAULT 'legacy'")
            if 'rule_version' not in columns:
                db.execute('ALTER TABLE signals ADD COLUMN rule_version INTEGER NOT NULL DEFAULT 1')
            db.execute('CREATE INDEX IF NOT EXISTS signals_wallet_detected ON signals(wallet,detected_at)')
            snap_columns={r['name'] for r in db.execute('PRAGMA table_info(snapshots)')}
            if 'market_cap_usd' not in snap_columns:
                db.execute('ALTER TABLE snapshots ADD COLUMN market_cap_usd REAL')
            db.execute("INSERT OR REPLACE INTO meta VALUES('schema_version','3')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).lastrowid

    def event(self, kind, message):
        self.execute('INSERT INTO events(at,kind,message) VALUES(?,?,?)', (time.time(), kind, message))

    def meta(self, key, value=None):
        if value is not None:
            self.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, json.dumps(value)))
        row = self.one('SELECT value FROM meta WHERE key=?', (key,))
        return json.loads(row['value']) if row else None
