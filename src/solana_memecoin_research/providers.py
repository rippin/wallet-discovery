from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .http import HttpClient, HttpError
from .models import Cluster, Holder

WSOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdYc1jNDFrTho7fi6Z1G7x7xVqTrSGTBAaS7w"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def is_solana_address(value: str) -> bool:
    """Return whether value is a base58 string decoding to a 32-byte public key."""
    if not value or any(character not in BASE58_ALPHABET for character in value):
        return False
    number = 0
    for character in value:
        number = number * 58 + BASE58_ALPHABET.index(character)
    decoded = (
        number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    )
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return len((b"\0" * leading_zeroes) + decoded) == 32


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class DexScreenerClient:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def token_market(self, mint: str, dex_url: str | None = None) -> dict[str, Any]:
        pairs = self.http.get_json(
            f"https://api.dexscreener.com/token-pairs/v1/solana/{mint}"
        )
        if not isinstance(pairs, list) or not pairs:
            return {
                "available": False,
                "status": "no_pair",
                "pairs": [],
                "selected_pair": None,
            }

        requested_pair = None
        if dex_url:
            requested_pair = dex_url.rstrip("/").split("/")[-1].split("?")[0]
        selected = None
        if requested_pair:
            selected = next(
                (pair for pair in pairs if pair.get("pairAddress") == requested_pair),
                None,
            )
        selected = selected or max(
            pairs, key=lambda pair: _as_float((pair.get("liquidity") or {}).get("usd"))
        )
        base = selected.get("baseToken") or {}
        quote = selected.get("quoteToken") or {}
        return {
            "available": True,
            "pair_count": len(pairs),
            "pair_address": selected.get("pairAddress"),
            "dex_id": selected.get("dexId"),
            "pair_url": selected.get("url"),
            "base_token": base,
            "quote_token": quote,
            "price_usd": _as_float(selected.get("priceUsd")),
            "price_native": _as_float(selected.get("priceNative")),
            "liquidity_usd": _as_float((selected.get("liquidity") or {}).get("usd")),
            "market_cap": _as_float(selected.get("marketCap")),
            "fdv": _as_float(selected.get("fdv")),
            "pair_created_at_ms": _as_int(selected.get("pairCreatedAt")),
            "volume": selected.get("volume") or {},
            "price_change": selected.get("priceChange") or {},
            "transactions": selected.get("txns") or {},
            "boosts": selected.get("boosts") or {},
            "info": selected.get("info") or {},
            "selected_pair": selected,
        }


class SolanaRpcClient:
    def __init__(self, http: HttpClient, rpc_url: str) -> None:
        self.http = http
        self.rpc_url = rpc_url
        self._request_id = 0

    def rpc(self, method: str, params: list[Any]) -> Any:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        response = self.http.post_json(self.rpc_url, payload)
        if response.get("error"):
            raise HttpError(f"Solana RPC {method} failed: {response['error']}")
        return response.get("result")

    def mint_info(self, mint: str) -> dict[str, Any]:
        result = self.rpc(
            "getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}]
        )
        value = (result or {}).get("value")
        if not value:
            return {"available": False, "status": "not_found"}
        owner_program = value.get("owner")
        parsed = ((value.get("data") or {}).get("parsed") or {})
        info = parsed.get("info") or {}
        extensions = info.get("extensions") or []
        return {
            "available": True,
            "program_id": owner_program,
            "program": (
                "SPL Token"
                if owner_program == TOKEN_PROGRAM
                else "Token-2022"
                if owner_program == TOKEN_2022_PROGRAM
                else "unknown"
            ),
            "decimals": _as_int(info.get("decimals")),
            "supply_raw": _as_int(info.get("supply")),
            "supply_ui": _as_int(info.get("supply"))
            / (10 ** _as_int(info.get("decimals"))),
            "mint_authority": info.get("mintAuthority"),
            "freeze_authority": info.get("freezeAuthority"),
            "is_initialized": bool(info.get("isInitialized", False)),
            "extensions": extensions,
            "raw_info": info,
        }

    def largest_holders(self, mint: str, supply_raw: int) -> list[Holder]:
        largest = self.rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        accounts = (largest or {}).get("value") or []
        addresses = [account["address"] for account in accounts]
        if not addresses:
            return []
        multiple = self.rpc(
            "getMultipleAccounts",
            [addresses, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        values = (multiple or {}).get("value") or []
        holders: list[Holder] = []
        for account, detail in zip(accounts, values):
            info = (
                ((((detail or {}).get("data") or {}).get("parsed") or {}).get("info"))
                or {}
            )
            raw = _as_int((account.get("amount")))
            ui_amount = _as_float(account.get("uiAmountString"))
            holders.append(
                Holder(
                    token_account=account["address"],
                    owner=info.get("owner"),
                    amount_raw=raw,
                    amount_ui=ui_amount,
                    share_pct=(raw / supply_raw * 100) if supply_raw else 0.0,
                )
            )
        return holders

    def signatures_for_address(self, address: str, limit: int) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        before = None
        while len(found) < limit:
            page_limit = min(1000, limit - len(found))
            config: dict[str, Any] = {"limit": page_limit, "commitment": "confirmed"}
            if before:
                config["before"] = before
            page = self.rpc("getSignaturesForAddress", [address, config]) or []
            if not page:
                break
            found.extend(page)
            before = page[-1]["signature"]
            if len(page) < page_limit:
                break
        return found

    def parsed_transaction(self, signature: str) -> dict[str, Any] | None:
        return self.rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )

    def early_activity(self, mint: str, signature_limit: int) -> dict[str, Any]:
        signatures = self.signatures_for_address(mint, signature_limit)
        complete = len(signatures) < signature_limit
        sampled = list(reversed(signatures[-min(80, len(signatures)) :]))
        buyers: dict[str, dict[str, Any]] = {}
        creator = None
        for index, item in enumerate(sampled):
            tx = self.parsed_transaction(item["signature"])
            if not tx:
                continue
            message = ((tx.get("transaction") or {}).get("message") or {})
            keys = message.get("accountKeys") or []
            fee_payer = next(
                (
                    key.get("pubkey")
                    for key in keys
                    if isinstance(key, dict) and key.get("signer")
                ),
                None,
            )
            if index == 0:
                creator = fee_payer
            meta = tx.get("meta") or {}
            pre = {
                (entry.get("owner"), entry.get("accountIndex")): _as_int(
                    ((entry.get("uiTokenAmount") or {}).get("amount"))
                )
                for entry in meta.get("preTokenBalances") or []
                if entry.get("mint") == mint and entry.get("owner")
            }
            post_entries = [
                entry
                for entry in meta.get("postTokenBalances") or []
                if entry.get("mint") == mint and entry.get("owner")
            ]
            for entry in post_entries:
                owner = entry["owner"]
                key = (owner, entry.get("accountIndex"))
                post_amount = _as_int((entry.get("uiTokenAmount") or {}).get("amount"))
                delta = post_amount - pre.get(key, 0)
                if delta > 0 and owner not in buyers:
                    buyers[owner] = {
                        "wallet": owner,
                        "amount_raw": delta,
                        "slot": tx.get("slot"),
                        "block_time": tx.get("blockTime"),
                        "signature": item["signature"],
                    }
        ordered = sorted(
            buyers.values(), key=lambda row: (row.get("slot") or 0, row["wallet"])
        )
        return {
            "creator_candidate": creator,
            "early_buyers": ordered[:20],
            "signature_count": len(signatures),
            "transactions_inspected": len(sampled),
            "history_complete": complete,
        }

    def funding_evidence(
        self, wallets: Iterable[str], transactions_per_wallet: int = 12
    ) -> dict[str, Any]:
        direct_edges: list[dict[str, str]] = []
        funders: dict[str, set[str]] = defaultdict(set)
        wallet_set = {wallet for wallet in wallets if wallet}
        for wallet in sorted(wallet_set):
            signatures = self.signatures_for_address(wallet, transactions_per_wallet)
            for signature in reversed(signatures):
                tx = self.parsed_transaction(signature["signature"])
                if not tx:
                    continue
                instructions = (
                    (((tx.get("transaction") or {}).get("message") or {}).get("instructions"))
                    or []
                )
                inner = [
                    instruction
                    for group in ((tx.get("meta") or {}).get("innerInstructions") or [])
                    for instruction in group.get("instructions") or []
                ]
                for instruction in [*instructions, *inner]:
                    parsed = instruction.get("parsed") if isinstance(instruction, dict) else None
                    if not isinstance(parsed, dict) or parsed.get("type") != "transfer":
                        continue
                    info = parsed.get("info") or {}
                    source = info.get("source")
                    destination = info.get("destination")
                    if destination == wallet and source:
                        funders[source].add(wallet)
                        if source in wallet_set:
                            direct_edges.append(
                                {
                                    "source": source,
                                    "destination": wallet,
                                    "signature": signature["signature"],
                                }
                            )
        shared = [
            {"funder": funder, "wallets": sorted(children)}
            for funder, children in funders.items()
            if len(children) > 1
        ]
        return {"direct_edges": direct_edges, "shared_funders": shared}


class JupiterClient:
    def __init__(self, http: HttpClient, api_key: str | None = None) -> None:
        self.http = http
        self.api_key = api_key

    def sell_quote(self, mint: str, amount_raw: int) -> dict[str, Any]:
        base = (
            "https://api.jup.ag/swap/v1/quote"
            if self.api_key
            else "https://lite-api.jup.ag/swap/v1/quote"
        )
        headers = {"x-api-key": self.api_key} if self.api_key else None
        response = self.http.get_json(
            base,
            params={
                "inputMint": mint,
                "outputMint": WSOL_MINT,
                "amount": amount_raw,
                "slippageBps": 100,
                "restrictIntermediateTokens": "true",
                "instructionVersion": "V2",
            },
            headers=headers,
        )
        return {
            "available": True,
            "input_amount_raw": _as_int(response.get("inAmount")),
            "output_amount_raw": _as_int(response.get("outAmount")),
            "minimum_output_raw": _as_int(response.get("otherAmountThreshold")),
            "price_impact_pct": _as_float(response.get("priceImpactPct")) * 100,
            "route_count": len(response.get("routePlan") or []),
            "context_slot": response.get("contextSlot"),
        }


class BirdeyeClient:
    def __init__(self, http: HttpClient, api_key: str) -> None:
        self.http = http
        self.api_key = api_key

    def top_traders(self, mint: str) -> dict[str, Any]:
        response = self.http.get_json(
            "https://public-api.birdeye.so/defi/v2/tokens/top_traders",
            params={
                "address": mint,
                "time_frame": "all",
                "sort_by": "realized_pnl",
                "sort_type": "desc",
                "offset": 0,
                "limit": 20,
            },
            headers={"X-API-KEY": self.api_key, "x-chain": "solana"},
        )
        payload = response.get("data") or {}
        items = payload.get("items") if isinstance(payload, dict) else payload
        items = items if isinstance(items, list) else []
        normalized = []
        for item in items:
            wallet = item.get("owner") or item.get("wallet") or item.get("address")
            realized = _as_float(
                item.get("realized_pnl")
                or item.get("realizedPnl")
                or item.get("pnl")
            )
            average_buy = _as_float(
                item.get("average_buy_price")
                or item.get("avg_buy_price")
                or item.get("averageBuyPrice")
            )
            average_sell = _as_float(
                item.get("average_sell_price")
                or item.get("avg_sell_price")
                or item.get("averageSellPrice")
            )
            normalized.append(
                {
                    "wallet": wallet,
                    "realized_pnl_usd": realized,
                    "unrealized_pnl_usd": _as_float(
                        item.get("unrealized_pnl") or item.get("unrealizedPnl")
                    ),
                    "volume_usd": _as_float(
                        item.get("volume_usd") or item.get("volumeUsd")
                    ),
                    "trade_count": _as_int(
                        item.get("trade_count") or item.get("tradeCount")
                    ),
                    "tags": item.get("wallet_tags") or item.get("tags") or [],
                    "average_buy_price": average_buy,
                    "average_sell_price": average_sell,
                    "observed_roi_pct": (
                        (average_sell / average_buy - 1) * 100
                        if average_buy > 0 and average_sell > 0
                        else None
                    ),
                    "first_trade_time": item.get("first_trade_time")
                    or item.get("firstTradeTime"),
                    "last_trade_time": item.get("last_trade_time")
                    or item.get("lastTradeTime"),
                }
            )
        return {"available": True, "top_traders": normalized}

    def wallet_pnl_summary(self, wallet: str) -> dict[str, Any]:
        response = self.http.get_json(
            "https://public-api.birdeye.so/wallet/v2/pnl/summary",
            params={
                "wallet": wallet,
                "duration": "all",
                "position_scope": "cumulative",
            },
            headers={"X-API-KEY": self.api_key, "x-chain": "solana"},
        )
        data = response.get("data") or {}
        counts = data.get("counts") or {}
        pnl = data.get("pnl") or {}
        cashflow = data.get("cashflow_usd") or data.get("cashflowUsd") or {}
        win_rate = _as_float(counts.get("win_rate") or counts.get("winRate"))
        if 0 < win_rate <= 1:
            win_rate *= 100
        return {
            "wallet": wallet,
            "available": True,
            "total_trades": _as_int(
                counts.get("total_trade")
                or counts.get("totalTrade")
                or data.get("total_trade")
            ),
            "wins": _as_int(counts.get("total_win") or counts.get("totalWin")),
            "losses": _as_int(counts.get("total_loss") or counts.get("totalLoss")),
            "win_rate_pct": win_rate,
            "realized_pnl_usd": _as_float(
                pnl.get("realized_profit_usd")
                or pnl.get("realizedProfitUsd")
                or data.get("realized_profit_usd")
            ),
            "unrealized_pnl_usd": _as_float(
                pnl.get("unrealized_usd")
                or pnl.get("unrealizedUsd")
                or data.get("unrealized_usd")
            ),
            "total_invested_usd": _as_float(
                cashflow.get("total_invested") or cashflow.get("totalInvested")
            ),
            "current_value_usd": _as_float(
                cashflow.get("current_value") or cashflow.get("currentValue")
            ),
            "source_scope": "Birdeye all-time wallet P&L summary",
        }


class XClient:
    def __init__(self, http: HttpClient, bearer_token: str) -> None:
        self.http = http
        self.bearer_token = bearer_token

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"https?://\S+", "", text.lower())
        text = re.sub(r"[@#$]\w+", "", text)
        text = re.sub(r"\d+(?:\.\d+)?", "", text)
        return " ".join(text.split())

    def recent_signal(self, mint: str, symbol: str | None) -> dict[str, Any]:
        terms = [f'"{mint}"']
        if symbol and len(symbol) >= 2:
            escaped = re.sub(r"[^A-Za-z0-9_]", "", symbol)
            if escaped:
                terms.append(f'"${escaped}"')
        query = f"({' OR '.join(terms)}) -is:retweet"
        response = self.http.get_json(
            "https://api.x.com/2/tweets/search/recent",
            params={
                "query": query,
                "max_results": 100,
                "tweet.fields": "created_at,public_metrics,author_id,lang",
                "expansions": "author_id",
                "user.fields": "created_at,public_metrics,username,verified",
            },
            headers={"Authorization": f"Bearer {self.bearer_token}"},
        )
        posts = response.get("data") or []
        users = {
            user["id"]: user for user in (response.get("includes") or {}).get("users") or []
        }
        authors = Counter(post.get("author_id") for post in posts if post.get("author_id"))
        normalized = [self._normalize_text(post.get("text", "")) for post in posts]
        hashes = Counter(
            hashlib.sha256(text.encode()).hexdigest() for text in normalized if text
        )
        repeated = sum(count for count in hashes.values() if count > 1)
        engagement = 0
        for post in posts:
            metrics = post.get("public_metrics") or {}
            engagement += sum(
                _as_int(metrics.get(key))
                for key in ("like_count", "retweet_count", "reply_count", "quote_count")
            )
        now = datetime.now(timezone.utc)
        ages = []
        for user in users.values():
            try:
                created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
                ages.append((now - created).days)
            except (KeyError, ValueError):
                pass
        return {
            "available": True,
            "query": query,
            "post_count": len(posts),
            "unique_authors": len(authors),
            "top_author_share_pct": (
                max(authors.values()) / len(posts) * 100 if posts and authors else 0.0
            ),
            "duplicate_share_pct": repeated / len(posts) * 100 if posts else 0.0,
            "engagement_total": engagement,
            "median_account_age_days": (
                sorted(ages)[len(ages) // 2] if ages else None
            ),
            "window": "recent X search (up to 7 days)",
        }


def build_clusters(
    holders: list[Holder],
    early_buyers: list[dict[str, Any]],
    funding: dict[str, Any] | None,
) -> list[Cluster]:
    shares = defaultdict(float)
    for holder in holders:
        if holder.owner:
            shares[holder.owner] += holder.share_pct
    parents: dict[str, str] = {wallet: wallet for wallet in shares}

    def find(wallet: str) -> str:
        parents.setdefault(wallet, wallet)
        while parents[wallet] != wallet:
            parents[wallet] = parents[parents[wallet]]
            wallet = parents[wallet]
        return wallet

    reasons: dict[str, list[str]] = defaultdict(list)

    def union(left: str, right: str, reason: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parents[root_right] = root_left
        reasons[find(left)].append(reason)

    if funding:
        for edge in funding.get("direct_edges") or []:
            union(
                edge["source"],
                edge["destination"],
                f"direct on-chain transfer {edge['signature']}",
            )
        for shared in funding.get("shared_funders") or []:
            wallets = shared["wallets"]
            for wallet in wallets[1:]:
                union(
                    wallets[0],
                    wallet,
                    f"shared observed funder {shared['funder']}",
                )

    # Entry within the same slot is only weak evidence and does not merge wallets.
    same_slot = Counter(
        buyer.get("slot") for buyer in early_buyers if buyer.get("slot") is not None
    )
    weak_wallets = {
        buyer["wallet"]
        for buyer in early_buyers
        if same_slot.get(buyer.get("slot"), 0) > 1
    }

    grouped: dict[str, list[str]] = defaultdict(list)
    for wallet in shares:
        grouped[find(wallet)].append(wallet)
    clusters = []
    for index, (root, wallets) in enumerate(
        sorted(grouped.items(), key=lambda item: -sum(shares[w] for w in item[1])), 1
    ):
        cluster_reasons = reasons.get(root, [])
        confidence = (
            "confirmed on-chain link"
            if any("direct on-chain" in reason for reason in cluster_reasons)
            else "strong behavioral link"
            if cluster_reasons
            else "weak correlation"
            if any(wallet in weak_wallets for wallet in wallets)
            else "unclustered"
        )
        if confidence == "weak correlation":
            cluster_reasons = ["same-slot early entry; not sufficient to merge wallets"]
        clusters.append(
            Cluster(
                cluster_id=f"C{index}",
                wallets=sorted(wallets),
                share_pct=sum(shares[wallet] for wallet in wallets),
                confidence=confidence,
                reasons=cluster_reasons,
            )
        )
    return clusters
