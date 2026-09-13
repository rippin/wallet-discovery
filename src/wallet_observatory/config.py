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
    discovery_sample: int = 8
    wallets_per_cycle: int = 8
    page_limit: int = 50
    max_pages: int = 2
    market_cap: int = 120

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
                   cycle_seconds=max(60, int(os.getenv('OBS_CYCLE_SECONDS', '300'))))
