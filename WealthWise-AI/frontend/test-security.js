const test = require("node:test");
const assert = require("node:assert/strict");
const { isSameOriginMutation, isAllowedUpload } = require("./utils/security");

function request({ origin, referer, host = "wealthwise.example", protocol = "https" } = {}) {
    const headers = { origin, referer, host };
    return {
        protocol,
        get(name) {
            return headers[name.toLowerCase()];
        }
    };
}

test("accepts same-origin mutation requests", () => {
    assert.equal(isSameOriginMutation(request({
        origin: "https://wealthwise.example"
    })), true);
});

test("accepts same-origin Referer when Origin is absent", () => {
    assert.equal(isSameOriginMutation(request({
        referer: "https://wealthwise.example/profile"
    })), true);
});

test("rejects cross-origin mutation requests", () => {
    assert.equal(isSameOriginMutation(request({
        origin: "https://attacker.example"
    })), false);
});

test("rejects requests without Origin or Referer", () => {
    assert.equal(isSameOriginMutation(request()), false);
});

test("rejects malformed origin values", () => {
    assert.equal(isSameOriginMutation(request({
        origin: "not-a-url"
    })), false);
});

test("accepts a PDF only when its signature matches", () => {
    assert.equal(isAllowedUpload({
        originalname: "statement.pdf",
        buffer: Buffer.from("%PDF-1.7 sample")
    }), true);
    assert.equal(isAllowedUpload({
        originalname: "statement.pdf",
        buffer: Buffer.from("not a pdf")
    }), false);
});

test("accepts XLSX ZIP signatures and rejects renamed arbitrary files", () => {
    assert.equal(isAllowedUpload({
        originalname: "portfolio.xlsx",
        buffer: Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x14])
    }), true);
    assert.equal(isAllowedUpload({
        originalname: "portfolio.xlsx",
        buffer: Buffer.from("plain text")
    }), false);
});

test("rejects unsupported extensions and missing buffers", () => {
    assert.equal(isAllowedUpload({
        originalname: "script.exe",
        buffer: Buffer.from("MZ")
    }), false);
    assert.equal(isAllowedUpload({
        originalname: "empty.pdf"
    }), false);
});
