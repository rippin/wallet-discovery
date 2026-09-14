from dataclasses import dataclass
import os

@dataclass
class Config:
    db: str = 'data/observatory.sqlite3'
    host: str = '127.0.0.1'
    port: int = 8080
    password: str = 'password123'
    rpc_url: str = ''
    live: bool = False
    monthly_credits: int = 900_000
    rpc_credit_cost: int = 10  # conservative upper bound; adjustable for your provider
    cycle_seconds: int = 300
    discovery_interval: int = 30
    discovery_requests: int = 6
    discovery_page_size: int = 1000
    discovery_max_pages: int = 2
    discovery_queue_cap: int = 20000
    discovery_max_age: int = 600
    min_market_cap: float = 10000
    min_purchase_usd: float = 100
    wallets_per_cycle: int = 8
    page_limit: int = 50
    max_pages: int = 2
    market_cap: int = 120
    focus_wallets: int = 3
    focus_seconds: int = 120
    research_seconds: int = 60
    jupiter_api_key: str = ''
    quote_daily_cap: int = 100


    @classmethod
    def env(cls):
        key = os.getenv('HELIUS_API_KEY', '')
        return cls(db=os.getenv('OBS_DB', cls.db), host=os.getenv('OBS_HOST', cls.host),
                   port=int(os.getenv('OBS_PORT', '8080')),
                   password=os.getenv('OBS_PASSWORD') or cls.password,
                   rpc_url=os.getenv('OBS_RPC_URL', '') or (f'https://mainnet.helius-rpc.com/?api-key={key}' if key else ''),
                   live=os.getenv('OBS_LIVE', '0') == '1',
                   monthly_credits=int(os.getenv('OBS_MONTHLY_CREDITS', '900000')),
                   rpc_credit_cost=int(os.getenv('OBS_RPC_CREDIT_COST', '10')),
                   cycle_seconds=max(60, int(os.getenv('OBS_CYCLE_SECONDS', '300'))),
                   discovery_interval=max(10,int(os.getenv('OBS_DISCOVERY_SECONDS','30'))),
                   discovery_requests=max(3,min(100,int(os.getenv('OBS_DISCOVERY_REQUESTS','6')))),
                   discovery_max_age=max(60,int(os.getenv('OBS_DISCOVERY_MAX_AGE_SECONDS','600'))),
                   focus_wallets=max(0,min(10,int(os.getenv('OBS_FOCUS_WALLETS','3')))),
                   focus_seconds=max(60,int(os.getenv('OBS_FOCUS_SECONDS','120'))),
                   research_seconds=max(30,int(os.getenv('OBS_RESEARCH_SECONDS','60'))),
                   jupiter_api_key=os.getenv('JUPITER_API_KEY',''),
                   quote_daily_cap=max(0,min(1000,int(os.getenv('OBS_QUOTE_DAILY_CAP','100')))),
                   min_market_cap=max(0,float(os.getenv('OBS_MIN_MARKET_CAP_USD','10000'))),
                   min_purchase_usd=max(0,float(os.getenv('OBS_MIN_PURCHASE_USD','100'))))
