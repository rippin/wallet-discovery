"""Conservative swap observations; never interprets a plain transfer as profit."""
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

PUMP = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
LAB = 'LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj'
WSOL = 'So11111111111111111111111111111111111111112'
USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
USDT = 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
QUOTES = {WSOL, USDC, USDT}
PROGRAMS = {PUMP:'pumpfun', LAB:'launchlab',
 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA':'pumpswap',
 'CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C':'raydium-cpmm',
 'CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK':'raydium-clmm',
 '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8':'raydium-amm',
 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4':'jupiter'}
IDL = json.loads(Path(__file__).with_name('instructions.json').read_text())
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def b58decode(value):
    n = 0
    for c in value:
        n = n * 58 + ALPHABET.index(c)
    return b'\0' * (len(value)-len(value.lstrip('1'))) + (n.to_bytes((n.bit_length()+7)//8, 'big') if n else b'')

def address(value):
    try:
        return isinstance(value, str) and 32 <= len(value) <= 44 and len(b58decode(value)) == 32
    except (ValueError, TypeError):
        return False

ANCHOR_SWAPS = {hashlib.sha256(('global:'+n).encode()).digest()[:8] for n in (
 'buy','buy_exact_quote_in','buy_exact_quote_in_v2','sell','swap','swap_v2','swap_base_input','swap_base_output',
 'route','shared_accounts_route','exact_out_route','shared_accounts_exact_out_route','route_with_token_ledger',
 'shared_accounts_route_with_token_ledger')}

def parse(tx, known_mints=()):
    if not tx or not tx.get('meta') or tx['meta'].get('err') is not None:
        return [], [], 'failed_or_missing'
    meta = tx['meta']; message = tx['transaction']['message']
    keys = message['accountKeys']
    keys = [k if isinstance(k, dict) else {'pubkey': k, 'signer': False} for k in keys]
    instructions = list(message.get('instructions', []))
    for group in meta.get('innerInstructions') or []:
        instructions.extend(group.get('instructions', []))
    recognized = []
    for ix in instructions:
        program = ix.get('programId')
        if not program and 'programIdIndex' in ix:
            program = keys[ix['programIdIndex']]['pubkey']
        if program not in PROGRAMS:
            continue
        try:
            data = b58decode(ix.get('data', ''))
        except ValueError:
            continue
        venue = PROGRAMS[program]
        platform = None
        mapping = {}
        spec = None
        if venue in IDL:
            spec = IDL[venue].get(data[:8].hex())
            if not spec:
                continue
            accounts = ix.get('accounts', [])
            accounts = [keys[a]['pubkey'] if isinstance(a,int) else a for a in accounts]
            if len(accounts) < len(spec['accounts']):
                continue
            mapping = dict(zip(spec['accounts'], accounts))
            platform = mapping.get('platform_config')
        elif not (data[:8] in ANCHOR_SWAPS or (venue == 'raydium-amm' and data[:1] in (b'\x09', b'\x0b'))):
            continue
        recognized.append({'venue':venue,'platform':platform,
                           'base':mapping.get('base_token_mint') or mapping.get('base_mint') or mapping.get('mint'),
                           'quote':mapping.get('quote_token_mint') or mapping.get('quote_mint') or (WSOL if venue=='pumpfun' else None),
                           'user':mapping.get('user') or mapping.get('payer'),
                           'side':('buy' if spec['name'].startswith('buy') else 'sell') if spec else None})
    links = []
    # Direct outer system transfers only: no pool flows or inferred ownership merges.
    for ix in message.get('instructions', []):
        p = ix.get('parsed') or {}
        if ix.get('program') == 'system' and p.get('type') == 'transfer':
            info = p['info']
            links.append({'source':info['source'], 'target':info['destination'],
                          'amount':info.get('lamports',0)/1e9, 'kind':'direct SOL transfer; ownership unproven'})
    if not recognized:
        return [], links, 'transfer_or_unsupported'
    deltas = defaultdict(lambda: defaultdict(Decimal))
    for label, sign in [('preTokenBalances',-1), ('postTokenBalances',1)]:
        for b in meta.get(label) or []:
            if b.get('owner'):
                amount = b['uiTokenAmount']
                deltas[b['owner']][b['mint']] += sign*Decimal(amount['amount'])/(10**amount['decimals'])
    trades = []
    for index,key in enumerate(keys):
        if not key.get('signer'):
            continue
        wallet = key['pubkey']; changes = deltas[wallet]
        # Combine native and wrapped SOL movement; native value is only an estimate
        # because rent/tips/other native transfers can share this transaction.
        native = Decimal(meta['postBalances'][index]-meta['preBalances'][index])/10**9
        if index == 0:
            native += Decimal(meta.get('fee',0))/10**9
        changes[WSOL] += native
        explicit=[r for r in recognized if r['base'] and r['user']==wallet]
        if explicit:
            identities={(r['base'],r['quote'],r['side']) for r in explicit}
            if len(identities)!=1:
                continue
            observation=explicit[0]
            assets=[(observation['base'],changes[observation['base']])]
            quote=[(observation['quote'],changes[observation['quote']])]
        else:
            # A decoded launchpad instruction for somebody else cannot explain this signer's balances.
            generic=[r for r in recognized if not r['base']]
            if not generic:
                continue
            observation=generic[0]
            changed={m:q for m,q in changes.items() if abs(q)>Decimal('0.000001')}
            tracked=[m for m in changed if m in known_mints and m not in QUOTES]
            if len(tracked)==1:
                assets=[(tracked[0],changed[tracked[0]])]
                quote=[(m,q) for m,q in changed.items() if m!=tracked[0]]
            else:
                assets=[(m,q) for m,q in changed.items() if m not in QUOTES]
                quote=[(m,q) for m,q in changed.items() if m in QUOTES]
        if len(assets) != 1:
            continue
        mint, qty = assets[0]
        opposite = [(m,q) for m,q in quote if q*qty < 0]
        if len(opposite) != 1:
            continue
        qm, qq = opposite[0]
        venue,platform=observation['venue'],observation['platform']
        if observation['side'] and observation['side']!=('buy' if qty>0 else 'sell'):
            continue
        trades.append({'wallet':wallet,'mint':mint,'side':'buy' if qty>0 else 'sell',
                       'quantity':float(abs(qty)), 'quote_mint':qm,'quote_quantity':float(abs(qq)),
                       'venue':venue,'platform':platform,
                       'quality':'balance-delta estimate; native costs may include rent/tips' if qm==WSOL else 'balance-delta observation'})
    return trades, links, 'swap_observed' if trades else 'ambiguous_swap'
