import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent / "snapshots"
INTERVAL_SECONDS = 5


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_array(value):
    """Gamma returns some arrays as JSON-encoded strings."""
    return json.loads(value) if isinstance(value, str) else value


def get_json(session, url, params):
    response = session.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_outcome(session, outcome, token_id):
    details = {"outcome": outcome, "tokenId": token_id}
    try:
        book = get_json(
            session, "https://clob.polymarket.com/book", {"token_id": token_id}
        )
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        best_bid = max(bids, key=lambda level: float(level["price"]), default=None)
        best_ask = min(asks, key=lambda level: float(level["price"]), default=None)
        bid_price = float(best_bid["price"]) if best_bid else None
        ask_price = float(best_ask["price"]) if best_ask else None
        details.update({
            "bestBid": bid_price,
            "bestAsk": ask_price,
            "bestBidSize": float(best_bid["size"]) if best_bid else None,
            "bestAskSize": float(best_ask["size"]) if best_ask else None,
            "spread": round(ask_price - bid_price, 10)
            if bid_price is not None and ask_price is not None else None,
            "orderBook": book,
        })
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        details["error"] = str(error)
        print(f"Could not fetch {outcome} order book: {error}", flush=True)
    details["fetchedAt"] = utc_now()
    return details


def collect_snapshot(session, slug):
    started_at = utc_now()
    events = get_json(
        session, "https://gamma-api.polymarket.com/events", {"slug": slug}
    )
    if not events:
        print(f"No market found for {slug}; will retry.", flush=True)
        return 0

    saved = 0
    for event in events:
        for market in event.get("markets", []):
            outcomes = parse_array(market.get("outcomes", []))
            token_ids = parse_array(market.get("clobTokenIds", []))
            if len(outcomes) != len(token_ids) or not outcomes:
                raise ValueError(f"Missing or mismatched outcomes/tokens for {market['id']}")

            snapshot = {
                "collectionStartedAt": started_at,
                "slug": slug,
                "eventId": event["id"],
                "marketId": market["id"],
                "question": market.get("question"),
                "eventStartTime": market.get("eventStartTime"),
                "endDate": market.get("endDate"),
                "closed": market.get("closed"),
                "acceptingOrders": market.get("acceptingOrders"),
            }
            for outcome, token_id in zip(outcomes, token_ids):
                snapshot[outcome.lower()] = fetch_outcome(session, outcome, token_id)
            # Outcomes are fetched sequentially; each has its own retrieval time.
            snapshot["fetchedAt"] = utc_now()
            output_path = OUTPUT_DIR / f"{slug}.jsonl"
            with output_path.open("a", encoding="utf-8") as output_file:
                output_file.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
            saved += 1
            print(f"Saved snapshot to {output_path.name}", flush=True)
    return saved


def main():
    parser = argparse.ArgumentParser(description="Collect Bitcoin 15-minute market snapshots.")
    parser.add_argument("--once", action="store_true", help="Collect one snapshot and exit.")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving snapshots in {OUTPUT_DIR}. Press Ctrl+C to stop.", flush=True)
    with requests.Session() as session:
        try:
            while True:
                cycle_start = time.monotonic()
                window_start = (int(time.time()) // 900) * 900
                slug = f"btc-updown-15m-{window_start}"
                try:
                    collect_snapshot(session, slug)
                except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                    print(f"Collection failed for {slug}: {error}", flush=True)
                    if args.once:
                        raise
                if args.once:
                    break
                # Slow requests may make a cycle longer than five seconds.
                time.sleep(max(0, INTERVAL_SECONDS - (time.monotonic() - cycle_start)))
        except KeyboardInterrupt:
            print("\nSnapshot collection stopped.", flush=True)


if __name__ == "__main__":
    main()
