const crypto = require("crypto");

function createRateLimiter({
    windowMs = 15 * 60 * 1000,
    max = 10,
    keyGenerator = req => req.ip || req.socket?.remoteAddress || "unknown",
    message = "Too many requests. Please try again later."
} = {}) {
    const buckets = new Map();

    return function rateLimit(req, res, next) {
        const now = Date.now();
        const key = String(keyGenerator(req) || "unknown");
        let bucket = buckets.get(key);

        if (!bucket || bucket.resetAt <= now) {
            bucket = { count: 0, resetAt: now + windowMs };
            buckets.set(key, bucket);
        }

        bucket.count += 1;

        // Opportunistic cleanup keeps the in-process store bounded.
        if (buckets.size > 5000) {
            for (const [storedKey, storedBucket] of buckets) {
                if (storedBucket.resetAt <= now) buckets.delete(storedKey);
            }
        }

        res.set("RateLimit-Limit", String(max));
        res.set("RateLimit-Remaining", String(Math.max(0, max - bucket.count)));
        res.set("RateLimit-Reset", String(Math.ceil(bucket.resetAt / 1000)));

        if (bucket.count > max) {
            res.set("Retry-After", String(Math.max(1, Math.ceil((bucket.resetAt - now) / 1000))));
            return res.status(429).send(message);
        }

        next();
    };
}

function authKey(req) {
    const ip = req.ip || req.socket?.remoteAddress || "unknown";
    const email = String(req.body?.email || "").trim().toLowerCase();
    const emailHash = email
        ? crypto.createHash("sha256").update(email).digest("hex")
        : "no-email";
    return `${ip}:${emailHash}`;
}

module.exports = { createRateLimiter, authKey };
