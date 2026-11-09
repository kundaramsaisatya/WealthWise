const test = require("node:test");
const assert = require("node:assert/strict");
const { selectAccountHolderSnapshots } = require("./utils/accountHolderSelection");

test("selects only snapshots belonging to the latest identified account holder", () => {
    const snapshots = [
        { documentName: "older person", accountHolder: "Person One", reportDate: "2026-01-01" },
        { documentName: "latest identity", accountHolder: "Jane Doe", reportDate: "2026-03-01" },
        { documentName: "same person", accountHolder: "  jane   doe ", reportDate: "2026-02-01" },
        { documentName: "unknown owner", accountHolder: null, reportDate: "2026-03-01" }
    ];

    const result = selectAccountHolderSnapshots(snapshots);

    assert.equal(result.activeAccountHolder, "Jane Doe");
    assert.deepEqual(
        result.snapshots.map(item => item.documentName),
        ["latest identity", "same person"]
    );
    assert.equal(result.excludedDocuments.length, 2);
    assert.equal(result.identityUnverified, false);
});

test("when no owner is identified, keeps only the newest snapshot", () => {
    const snapshots = [
        { documentName: "older", accountHolder: null, reportDate: "2026-01-01" },
        { documentName: "newest", accountHolder: "", reportDate: "2026-02-01" }
    ];

    const result = selectAccountHolderSnapshots(snapshots);

    assert.deepEqual(result.snapshots.map(item => item.documentName), ["newest"]);
    assert.equal(result.activeAccountHolder, null);
    assert.equal(result.excludedDocuments.length, 1);
    assert.equal(result.identityUnverified, true);
});

test("returns an empty selection for an empty input", () => {
    assert.deepEqual(selectAccountHolderSnapshots([]), {
        snapshots: [],
        activeAccountHolder: null,
        excludedDocuments: [],
        identityUnverified: false
    });
});

test("rejects malformed snapshot collections", () => {
    assert.throws(
        () => selectAccountHolderSnapshots(null),
        /must be an array/
    );
});
