const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ejs = require("ejs");

test("dashboard EJS template compiles with instrument NAV risk section", () => {
    const templatePath = path.join(__dirname, "views", "dashboard.ejs");
    const template = fs.readFileSync(templatePath, "utf8");

    assert.match(template, /Instrument NAV History/);
    assert.match(template, /volatility_per_observation_percentage/);
    assert.doesNotThrow(() => ejs.compile(template));
});
