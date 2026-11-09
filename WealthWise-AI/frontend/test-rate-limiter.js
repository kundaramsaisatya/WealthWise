const test = require("node:test");
const assert = require("node:assert/strict");
const { createRateLimiter, authKey } = require("./utils/rateLimiter");

function mockRequest(overrides = {}) {
    return {
        ip: "203.0.113.10",
        body: { email: "Person@Example.com" },
        ...overrides
    };
}

function mockResponse() {
    const headers = {};
    let statusCode = 200;
    let body;
    return {
        headers,
        get statusCode() { return statusCode; },
        get body() { return body; },
        set(name, value) { headers[name] = value; return this; },
        status(value) { statusCode = value; return this; },
        send(value) { body = value; return this; }
    };
}

test("allows requests within the configured limit", () => {
    const limiter = createRateLimiter({ windowMs: 60000, max: 2 });
    let nextCount = 0;
    for (let i = 0; i < 2; i++) {
        limiter(mockRequest(), mockResponse(), () => nextCount++);
    }
    assert.equal(nextCount, 2);
});

test("blocks requests above the configured limit", () => {
    const limiter = createRateLimiter({ windowMs: 60000, max: 1 });
    const next = () => {};
    limiter(mockRequest(), mockResponse(), next);
    const response = mockResponse();
    limiter(mockRequest(), response, next);
    assert.equal(response.statusCode, 429);
    assert.ok(Number(response.headers["Retry-After"]) > 0);
});

test("uses separate buckets for different IP and email combinations", () => {
    const limiter = createRateLimiter({ windowMs: 60000, max: 1 });
    const responseA = mockResponse();
    const responseB = mockResponse();
    limiter(mockRequest(), responseA, () => {});
    limiter(mockRequest({ ip: "203.0.113.11" }), responseB, () => {});
    assert.equal(responseB.statusCode, 200);
});

test("hashes email in the authentication rate-limit key", () => {
    const key = authKey(mockRequest());
    assert.equal(key.includes("person@example.com"), false);
    assert.ok(key.startsWith("203.0.113.10:"));
});

test("normalizes email casing and whitespace in the key", () => {
    assert.equal(
        authKey(mockRequest({ body: { email: " PERSON@example.com " } })),
        authKey(mockRequest())
    );
});

