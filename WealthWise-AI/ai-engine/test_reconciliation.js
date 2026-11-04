const assert = require("assert");

function isValidNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
}

function checkConflict(records) {
    const recordsByDate = new Map();
    const undatedRecords = [];

    const datedRecords = records
        .filter(record => {
            const date = record.reportDate
                ? new Date(record.reportDate)
                : null;

            return date && !Number.isNaN(date.getTime());
        })
        .sort((a, b) =>
            new Date(b.reportDate) - new Date(a.reportDate)
        );

    for (const record of records) {
        const date = record.reportDate
            ? new Date(record.reportDate)
            : null;

        if (!date || Number.isNaN(date.getTime())) {
            undatedRecords.push(record);
            continue;
        }

        const dateKey = date.toISOString().slice(0, 10);

        if (!recordsByDate.has(dateKey)) {
            recordsByDate.set(dateKey, []);
        }

        recordsByDate.get(dateKey).push(record);
    }

    let hasConflict = false;

    for (const dateRecords of recordsByDate.values()) {
        const values = [
            ...new Set(
                dateRecords
                    .map(record => record.currentValue)
                    .filter(isValidNumber)
                    .map(value => Number(value.toFixed(2)))
            )
        ];

        if (values.length > 1) {
            hasConflict = true;
            break;
        }
    }

    if (!hasConflict && undatedRecords.length > 0) {
        const undatedValues = [
            ...new Set(
                undatedRecords
                    .map(record => record.currentValue)
                    .filter(isValidNumber)
                    .map(value => Number(value.toFixed(2)))
            )
        ];

        if (undatedValues.length > 1) {
            hasConflict = true;
        }

        const latestDatedValue = datedRecords[0]?.currentValue;

        if (
            !hasConflict &&
            isValidNumber(latestDatedValue) &&
            undatedValues.some(
                value => Number(value.toFixed(2)) !==
                    Number(latestDatedValue.toFixed(2))
            )
        ) {
            hasConflict = true;
        }
    }

    return hasConflict;
}

// Test cases
const tests = [
    {
        name: "Same date, same value",
        records: [
            { reportDate: "2026-10-01", currentValue: 100000 },
            { reportDate: "2026-10-01", currentValue: 100000 }
        ],
        expected: false
    },
    {
        name: "Same date, different values",
        records: [
            { reportDate: "2026-10-01", currentValue: 100000 },
            { reportDate: "2026-10-01", currentValue: 120000 }
        ],
        expected: true
    },
    {
        name: "Different dates, different values",
        records: [
            { reportDate: "2026-10-01", currentValue: 100000 },
            { reportDate: "2026-10-02", currentValue: 120000 }
        ],
        expected: false
    },
    {
        name: "Undated records with different values",
        records: [
            { currentValue: 100000 },
            { currentValue: 120000 }
        ],
        expected: true
    },
    {
        name: "Undated value differs from latest dated value",
        records: [
            { reportDate: "2026-10-01", currentValue: 100000 },
            { reportDate: "2026-10-02", currentValue: 120000 },
            { currentValue: 90000 }
        ],
        expected: true
    },
    {
        name: "Undated value matches latest dated value",
        records: [
            { reportDate: "2026-10-01", currentValue: 100000 },
            { reportDate: "2026-10-02", currentValue: 120000 },
            { currentValue: 120000 }
        ],
        expected: false
    }
];

let passed = 0;

for (const test of tests) {
    const actual = checkConflict(test.records);
    const success = actual === test.expected;

    console.log(
        `${success ? "PASS" : "FAIL"}: ${test.name}`
    );

    if (!success) {
        console.log(
            `Expected: ${test.expected}, Received: ${actual}`
        );
    } else {
        passed++;
    }
}

console.log(`\nResult: ${passed}/${tests.length} tests passed`);

assert.strictEqual(passed, tests.length);