function normalizeAccountHolder(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ");
}

function getSnapshotDate(snapshot) {
    if (!snapshot || !snapshot.reportDate) {
        return new Date(0);
    }

    const parsed = new Date(snapshot.reportDate);
    return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
}

function selectAccountHolderSnapshots(snapshots) {
    if (!Array.isArray(snapshots)) {
        throw new TypeError("Portfolio snapshots must be an array.");
    }

    const identified = snapshots.filter(snapshot =>
        snapshot &&
        typeof snapshot.accountHolder === "string" &&
        snapshot.accountHolder.trim()
    );

    if (identified.length === 0) {
        const ordered = [...snapshots].sort((a, b) =>
            getSnapshotDate(b) - getSnapshotDate(a) ||
            new Date(b?.createdAt || 0) - new Date(a?.createdAt || 0)
        );
        const selected = ordered.length ? [ordered[0]] : [];
        const excludedDocuments = ordered.slice(1).map(snapshot => ({
            documentName: snapshot.documentName || "Unknown document",
            accountHolder: null,
            reportDate: snapshot.reportDate || null,
            reason: "Not combined because account-holder identity could not be verified."
        }));

        return {
            snapshots: selected,
            activeAccountHolder: null,
            excludedDocuments,
            identityUnverified: snapshots.length > 0
        };
    }

    const latestIdentified = [...identified].sort((a, b) =>
        getSnapshotDate(b) - getSnapshotDate(a) ||
        new Date(b.createdAt || 0) - new Date(a.createdAt || 0)
    )[0];

    const activeAccountHolder = latestIdentified.accountHolder.trim();
    const activeKey = normalizeAccountHolder(activeAccountHolder);
    const selected = snapshots.filter(snapshot =>
        normalizeAccountHolder(snapshot?.accountHolder) === activeKey
    );

    const excludedDocuments = snapshots
        .filter(snapshot =>
            normalizeAccountHolder(snapshot?.accountHolder) !== activeKey
        )
        .map(snapshot => ({
            documentName: snapshot.documentName || "Unknown document",
            accountHolder: snapshot.accountHolder || null,
            reportDate: snapshot.reportDate || null,
            reason: snapshot.accountHolder
                ? "Different account holder."
                : "Account holder could not be verified."
        }));

    return {
        snapshots: selected,
        activeAccountHolder,
        excludedDocuments,
        identityUnverified: false
    };
}

module.exports = { selectAccountHolderSnapshots };
