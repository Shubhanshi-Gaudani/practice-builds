# Rate Limiters: Notes & System Design Cheat Sheet

## TL;DR decision guide

| If you need… | Use |
|---|---|
| Average rate, bursts are OK (most public APIs) | **Token bucket** |
| Smooth, constant output rate (protect a fragile downstream) | **Leaky bucket** |
| Dead simple, rough limits, low traffic | **Fixed window counter** |
| Exact "max N in any rolling W seconds" | **Sliding window log** |
| Near-exact rolling limit at scale, O(1) memory | **Sliding window counter** (common production default) |
| Cap in-flight work, not request rate | **Concurrency limiter** |
| Expensive vs cheap requests cost differently | Any bucket with **weighted cost** (`allow(cost=n)`) |

---

## 1. Token bucket

**How:** A bucket holds up to `capacity` tokens and refills at `rate` tokens/sec. Each request spends `cost` tokens; if there aren't enough → reject (429). Refill lazily on each call: `tokens = min(capacity, tokens + elapsed * rate)`.

- **State per key:** 2 numbers (`tokens`, `last_refill`) → O(1)
- **Guarantees:** long-run average ≤ `rate`; bursts up to `capacity`
- **Pros:** burst-friendly, cheap, supports weighted costs, two intuitive knobs (rate + burst)
- **Cons:** no hard cap per window — idle user can burst `capacity`, then keep going at `rate` (≈ capacity + rate·W requests in a window W)
- **Use when:** public/partner APIs, API gateways, client-side throttling of your own outbound calls

> Built in `practice-builds/rate-limiter` → `TokenBucket`, `PerUserRateLimiter`

## 2. Leaky bucket

**How:** Requests enter a queue (the bucket) of fixed size and "leak" out (are processed) at a constant rate. Full bucket → reject. A "meter" variant just tracks the level and rejects instead of queueing — mathematically the mirror image of a token bucket.

- **State:** O(1) (meter) or O(queue size) (queue)
- **Pros:** perfectly smooth output; great for shaping traffic into something fragile
- **Cons:** queued variant adds latency; bursts get delayed, not served
- **Use when:** traffic shaping, protecting a slow backend/DB, network egress

## 3. Fixed window counter

**How:** Counter per key per window (e.g. `user:42:2026-10-22T20:51`). Increment; if > limit, reject. Counter resets when the window rolls over.

- **State:** O(1) — one integer (Redis `INCR` + `EXPIRE`)
- **Pros:** simplest possible, trivially distributed
- **Cons:** **boundary burst** — `limit` requests at 11:59:59 + `limit` at 12:00:00 = **2× limit in ~1 second**
- **Use when:** coarse quotas (per hour/day), low stakes, quick MVP

## 4. Sliding window log

**How:** Store a timestamp for every allowed request. On each call, drop timestamps older than `now - window`, then allow if `count < limit`.

- **State:** O(limit) timestamps per key (deque in memory; Redis sorted set in prod)
- **Pros:** exact — never more than N in *any* rolling window
- **Cons:** memory grows with limit × users; more work per request
- **Use when:** strict quotas, billing-sensitive limits, low-to-moderate limits per user, abuse prevention (login attempts, OTP sends)

> Built in `practice-builds/rate-limiter` → `SlidingWindowLimiter`

## 5. Sliding window counter (hybrid)

**How:** Keep only the current and previous fixed-window counts. Estimate the rolling count as:

```
estimate = prev_count * (1 - elapsed_in_current / window) + curr_count
```

Assumes requests in the previous window were evenly spread.

- **State:** O(1) — two integers
- **Pros:** fixes the fixed-window boundary burst at fixed-window cost; tiny error in practice
- **Cons:** approximate; slightly harder to explain
- **Use when:** high-scale edge/API limiting where log memory is too expensive — the usual "best default" answer in interviews

## 6. Concurrency limiter

**How:** Counter of in-flight requests per key; increment on start, decrement on finish; reject if at max.

- Limits **simultaneous** work, not rate — protects against slow, expensive requests piling up
- Often layered *with* a rate limiter

---

## Who uses what (as of Oct 2026, per public docs)

| Company / tool | Approach | Details |
|---|---|---|
| **AWS API Gateway** | Token bucket | "Rate" = refill rate (RPS), "burst" = bucket capacity; applied at account/region, stage/method, and per-API-key usage plans |
| **Shopify** | Leaky bucket | REST Admin: bucket of 40 requests per app per store, leaking 2/sec (10× on Plus). GraphQL: same bucket idea but each query costs "points" based on calculated query cost |
| **Cloudflare** | Sliding window counter | Edge rate limiting; 2017 engineering blog describes the two-counter approximation |
| **NGINX** (`limit_req`) | Leaky bucket | Stock module; `burst` param sets queue size |
| **GitHub** | Fixed window + secondary limits | Primary: 5,000 req/hr per authenticated user (60/hr unauthenticated), reset time in `x-ratelimit-reset`. Secondary: points-per-minute per endpoint + max 100 concurrent requests. GraphQL uses cost-based points |
| **Stripe** | Rate limiter + concurrency limiter | Docs list both limiter types; recommends clients use a token bucket on their side |

**Pattern to notice:** big APIs layer several limiters — a primary rate limit, a concurrency limit, and cost-based weighting for expensive operations.

---

## Distributed rate limiter design (in-memory → Redis)

Our `PerUserRateLimiter` keeps buckets in a Python dict. That breaks the moment there's more than one server: with 5 gateways behind a load balancer, each one sees ~1/5 of a user's traffic, so a "100/min" limit quietly becomes ~500/min. The fix is **shared state in Redis**, plus everything needed to make Redis fast, correct, and survivable.

### Requirements to state up front (example numbers)

- Identify clients by user ID / IP / API key; configurable rules; 429 + headers on reject
- **Scale:** ~1M req/s, ~100M DAU
- **Latency:** < ~10 ms added per request (ideally ~1 ms)
- **Availability over consistency:** slightly-off limits across nodes are fine; a dead API is not

### Where the limiter lives

| Placement | Pros | Cons |
|---|---|---|
| **In-process** (each app server, local memory) | fastest, no dependencies | only sees local traffic → limit × N servers |
| **Dedicated rate-limit service** | global view, rich business context (tier, account status) | extra network hop on every request, another service to keep alive |
| **API gateway / load balancer** (usual answer) | rejects before traffic reaches app servers, central control | only knows what's in the request (headers, IP, JWT claims) — put tier in the JWT |

**Layer rules and enforce the most restrictive:** per-user, per-IP, per-endpoint, and a global ceiling. Blocked if *any* applicable rule says no.

### Data model in Redis

One hash per client per rule, holding exactly what our `TokenBucket` holds:

```
rl:{rule}:{client_id}  →  { tokens: 37.5, last: 1761184260.123 }   TTL ≈ 2 × capacity/rate
```

The TTL is the Redis version of our `cleanup()`: an idle bucket refills fully after `capacity / rate` seconds, so letting it expire after that is lossless.

### Correctness: the read-modify-write race

Naive flow: `HMGET` state → compute in the gateway → `HSET` new state. Two gateways handling the same user at the same instant both read "1 token", both allow, both write → 2 requests through on 1 token. Wrapping only the writes in `MULTI/EXEC` **doesn't fix it**, because the read happens outside the transaction.

**Fix: run the whole read → refill → decide → write in one Lua script.** Redis executes a script atomically (single-threaded, nothing interleaves), so the check-and-spend is one indivisible step. It's also one round trip instead of two.

```lua
-- token_bucket.lua
-- KEYS[1] = bucket key
-- ARGV[1] = capacity, ARGV[2] = rate (tokens/sec), ARGV[3] = cost
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])

-- Use Redis's clock, not each gateway's: avoids clock skew between servers (Redis 7+)
local t   = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1e6

local state  = redis.call('HMGET', KEYS[1], 'tokens', 'last')
local tokens = tonumber(state[1]) or capacity      -- new client starts full
local last   = tonumber(state[2]) or now

tokens = math.min(capacity, tokens + math.max(0, now - last) * rate)

local allowed = 0
if tokens >= cost then
  tokens  = tokens - cost
  allowed = 1
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate) * 2)

-- Lua numbers returned to Redis get truncated to integers, so send tokens as a string
return { allowed, tostring(tokens) }
```

It's the same logic as `TokenBucket._refill()` + `allow()`, just running inside Redis.

### Calling it from the gateway, with fail-fast + fallback

```python
import redis

class RedisRateLimiter:
    def __init__(self, client, capacity, rate, fallback):
        self.capacity = capacity
        self.rate = rate
        self.script = client.register_script(open("token_bucket.lua").read())  # EVALSHA under the hood
        self.fallback = fallback        # e.g. a local PerUserRateLimiter

    def allow(self, client_id, rule="default", cost=1):
        key = f"rl:{rule}:{client_id}"
        try:
            allowed, _remaining = self.script(keys=[key], args=[self.capacity, self.rate, cost])
            return allowed == 1
        except (redis.TimeoutError, redis.ConnectionError):
            return self.fallback.allow(client_id, cost)   # degrade, don't hang


pool = redis.ConnectionPool(
    host="redis-cluster", port=6379,
    socket_timeout=0.005,           # 5 ms: fail fast, never let the limiter stall a request
    socket_connect_timeout=0.005,
    max_connections=200,
)
client = redis.Redis(connection_pool=pool)
```

### Scaling Redis to ~1M req/s

- A single Redis node handles roughly 100k–200k simple ops/s; each check is a few ops → plan on ~50k–100k checks/s per node.
- **Shard by client key** so all of one client's state lives on one node: consistent hashing on user ID / IP / API key.
- In practice use **Redis Cluster**: keys map to 16,384 hash slots spread across nodes, and the client library routes automatically. ~10+ primaries covers 1M req/s with headroom.
- Lua scripts must touch keys on a single slot. One key per script call is fine; for multi-rule checks in one script, use **hash tags** (`rl:{alice}:per_min`, `rl:{alice}:per_hour`) so they co-locate.

### High availability

- **Primary + replicas per shard** with automatic failover (built into Redis Cluster; Redis Sentinel for non-cluster setups). A replica is promoted when its primary dies.
- **Replication is async**, so a failover can lose the last few ms of writes → some users briefly get a few extra tokens. For rate limiting that's an acceptable trade (AP over CP).
- Spread replicas across availability zones.
- Avoid persistence overhead you don't need: rate-limit state is ephemeral, so RDB/AOF can be relaxed or off — losing it just means everyone starts with a full bucket.

### Fault tolerance: when Redis is slow or down

1. **Fail fast:** tight client timeouts (a few ms). A slow limiter is worse than no limiter because it adds latency to *every* request.
2. **Circuit breaker:** after N consecutive Redis failures, stop calling it for a cool-down period and go straight to the fallback; probe periodically to recover. Prevents piling retries onto a struggling Redis.
3. **Choose the failure mode per endpoint:**

| Mode | Behaviour | Risk | Good for |
|---|---|---|---|
| **Fail open** | allow everything | Redis often fails *because* of a traffic spike — sending all of it downstream can collapse the backend | low-risk read endpoints, internal APIs |
| **Fail closed** | reject (429/503) | API effectively down; clients retry and add load | payments, login/OTP, security-sensitive paths |
| **Degrade to local limiter** (best of both) | each gateway enforces `limit / num_gateways` in memory | approximate, but bounded | most user-facing APIs |

4. **Alert** when the fallback path is active, so it's never silent.

### Latency

- **Connection pooling** (persistent TCP connections) — avoids a handshake per check; the biggest easy win.
- **One round trip per check** — Lua (or pipelining) instead of separate read/write calls.
- **Regional deployment** — gateways + Redis in each region, limits enforced per region. Cross-region sync is eventual (or split the global limit across regions).
- Local caching of limit state is possible but risky: stale reads mean wrong decisions.

### Hot keys

A single client (abusive or a legitimate heavy integration) can overload its shard.
- **Abusive:** auto-blocklist clients who keep hitting the limit (e.g. 10 rejections/min → block for a few minutes), checked locally in the gateway before touching Redis; DDoS protection (Cloudflare, AWS Shield) in front.
- **Legitimate:** encourage client-side throttling and batching; offer higher tiers or dedicated capacity.
- **Shared IPs** (NAT, corporate proxies, public Wi-Fi): set IP limits generously; lean on authenticated per-user limits.

### Dynamic rules

| Approach | How | Trade-off |
|---|---|---|
| **Poll** | rules in a DB/config service; gateways refresh every ~30s and cache locally | simple; changes take up to a poll interval to apply |
| **Push** | ZooKeeper/etcd watches or Redis pub/sub notify gateways instantly | near-instant (good for incident response); more moving parts, must handle missed updates |

### Drop vs queue

Fail fast with **429** for interactive APIs. Queuing excess requests uses memory, makes latency unpredictable, and clients retry anyway. Queuing only makes sense for batch/async work.

### Final architecture (one-liner)

`Client → (DDoS/CDN) → API gateway [blocklist check → Lua token bucket in Redis Cluster via pooled conns, 5 ms timeout, circuit breaker → local fallback] → app servers`, with rules pushed from a config service and Redis primaries replicated across AZs.

### Other production concerns

- **What's the key?** User ID, API key, IP, IP+endpoint, tenant.
- **Clock.** Monotonic clock locally; in distributed setups use the store's clock (Redis `TIME`) so gateway clock skew doesn't matter.
- **Where to enforce.** Edge/CDN → API gateway → service → per-method. Earlier = cheaper rejection.
- **Observability:** 429 rate per rule/client, Redis latency p99, fallback-mode alerts, shard hotspot metrics.

## Client-facing behaviour

- Return **HTTP 429 Too Many Requests**
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After`
- Clients should retry with **exponential backoff + jitter**

---

## Interview answer framework

1. **Clarify:** per user / IP / API key? Hard limit or average? Single node or distributed? What happens on reject (429 vs queue)?
2. **Pick algorithm** and justify the trade-off (burst tolerance vs precision vs memory).
3. **Data model:** what's stored per key, in what (Redis), with what TTL.
4. **Atomicity:** Lua script / atomic ops.
5. **Scale & failure:** sharding by key, fail open vs closed, local caching.
6. **API contract:** 429 + headers, client backoff.
7. **Extras:** tiered limits (free vs paid), weighted costs, concurrency limits, monitoring/alerting on 429 rates.

## One-line memory hooks

- **Token bucket:** saves up credit → allows bursts
- **Leaky bucket:** constant drip out → smooth
- **Fixed window:** resets on the clock → 2× at the boundary
- **Sliding log:** remembers every request → exact but heavy
- **Sliding counter:** two counters + weighting → near-exact and cheap

---

### Sources
- AWS API Gateway throttling: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-throttling.html
- Shopify REST Admin API rate limits: https://shopify.dev/docs/api/admin-rest/usage/rate-limits
- Shopify API limits overview: https://shopify.dev/docs/api/usage/limits
- Cloudflare, "How we built rate limiting capable of scaling to millions of domains": https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- GitHub REST API rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- GitHub GraphQL resource limitations: https://docs.github.com/graphql/overview/resource-limitations
- Stripe rate limits: https://docs.stripe.com/rate-limits
- Hello Interview, "Design a Distributed Rate Limiter": https://www.hellointerview.com/learn/system-design/problem-breakdowns/distributed-rate-limiter