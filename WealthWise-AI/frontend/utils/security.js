const path = require("path");

function isSameOriginMutation(req) {
    const suppliedOrigin = req.get("origin");
    const suppliedReferer = req.get("referer");

    let source;
    try {
        if (suppliedOrigin) {
            source = new URL(suppliedOrigin);
        } else if (suppliedReferer) {
            source = new URL(suppliedReferer);
        } else {
            return false;
        }

        const expected = new URL(`${req.protocol}://${req.get("host")}`);
        return source.origin === expected.origin;
    } catch {
        return false;
    }
}

function isAllowedUpload(file) {
    if (!file || !Buffer.isBuffer(file.buffer)) return false;

    const extension = path.extname(file.originalname || "").toLowerCase();
    const bytes = file.buffer;

    if (extension === ".pdf") {
        return bytes.length >= 5 &&
            bytes.subarray(0, 5).toString("ascii") === "%PDF-";
    }

    if (extension === ".xlsx") {
        // XLSX is an OOXML ZIP package. Reject arbitrary files renamed .xlsx.
        return bytes.length >= 4 &&
            bytes[0] === 0x50 &&
            bytes[1] === 0x4b &&
            bytes[2] === 0x03 &&
            bytes[3] === 0x04;
    }

    return false;
}

module.exports = {
    isSameOriginMutation,
    isAllowedUpload
};
