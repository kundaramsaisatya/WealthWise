const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("dashboard contains safely escaped instrument NAV risk insights", () => {
    const templatePath = path.join(__dirname, "views", "dashboard.ejs");
    const template = fs.readFileSync(templatePath, "utf8");

    assert.match(template, /Instrument NAV History/);
    assert.match(template, /Portfolio Risk Indicator/);
    assert.match(template, /Sector Exposure/);
    assert.match(template, /Issuer Exposure/);
    assert.match(template, /identified coverage/i);
    assert.match(template, /View calculation evidence/);
    assert.match(template, /Scoring methodology and limitations/);
    assert.match(template, /volatility_per_observation_percentage/);
    assert.match(template, /maximum drawdown/i);
    assert.match(template, /NAV change is not an investor return/);
    assert.doesNotMatch(template, /<%-\s*item\.(?:name|data_source|isin|folio_number|message)/);
});
