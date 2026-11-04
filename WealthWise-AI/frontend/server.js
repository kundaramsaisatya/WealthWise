
require("dotenv").config({
    path: require("path").join(__dirname, "../.env")
});

const express = require("express");
const axios = require("axios");
const multer = require("multer");
const FormData = require("form-data");
const path = require("path");
const session = require("express-session");
const MongoStore = require("connect-mongo").default;
const User = require("./models/User");
const bcrypt = require("bcryptjs");
const Chat = require("./models/Chat");
const mongoose = require("mongoose");
const crypto = require("crypto");
const fs = require("fs");
const Portfolio = require("./models/Portfolio");
const Document = require("./models/Document");
const connectDB = require("./config/database");
const GoalHoldingAllocation = require("./models/GoalHoldingAllocation");

const app = express();
const PORT = process.env.PORT || 3000;
const AI_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";

let sessionMiddleware;

app.use((req, res, next) => {
    if (!sessionMiddleware) {
        return res.status(503).send("Database is starting...");
    }

    sessionMiddleware(req, res, next);
});

app.use((req, res, next) => {
    res.locals.user = req.session.user || null;
    next();
});

const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 10 * 1024 * 1024 }
});

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, "public")));


//financialGoal
const FinancialGoal = require("./models/FinancialGoal");

const {
    calculateGoalPlan
} = require("./utils/goalCalculator");

//another
const {
    calculateGoalAssessment
} = require("./utils/goalAssessment");

// --------------------------------------------------
// SHARED HELPERS
// --------------------------------------------------

function getServiceHeaders() {
    return {
        "X-Service-Secret": process.env.AI_SERVICE_SECRET
    };
}

function isValidNumber(value) {
    return (
        typeof value === "number" &&
        Number.isFinite(value)
    );
}

function normalizeIdentifier(value) {
    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .trim()
        .toUpperCase()
        .replace(/\s+/g, "");
}

function normalizeName(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ");
}

function isDemoDocument(snapshot) {
    if (snapshot.isDemo === true) {
        return true;
    }

    return /demo|sample|illustrative/i.test(
        snapshot.documentName || ""
    );
}

function getSnapshotDate(snapshot) {
    // Only a statement/report date can establish valuation recency.
    // Upload time is not a substitute for the statement date.

    if (!snapshot.reportDate) {
        return new Date(0);
    }

    const parsed = new Date(snapshot.reportDate);

    return Number.isNaN(parsed.getTime())
        ? new Date(0)
        : parsed;
}


function getHoldingKey(holding, snapshot) {

    const isin = normalizeIdentifier(holding.isin);
    const folio = normalizeIdentifier(holding.folioNumber);
    const name = normalizeName(holding.name);

    const subCategory = String(
        holding.subCategory || ""
    ).trim().toLowerCase();

    // Listed stocks: use ISIN as the stable identity.
    // This remains consistent across different statement uploads.
    if (
        isin &&
        subCategory === "listed shares"
    ) {
        return `ISIN:${isin}|ASSET:LISTED`;
    }

    // Mutual funds and other folio-based investments.
    if (isin && folio) {
        return `ISIN:${isin}|FOLIO:${folio}`;
    }

    // Conservative fallback when ISIN is unavailable.
    if (folio && name) {
        return `FOLIO:${folio}|NAME:${name}`;
    }

    // Never merge using name alone.
    return `DOCUMENT:${snapshot._id}|HOLDING:${holding._id || crypto.randomUUID()}`;
}



// --------------------------------------------------
// PORTFOLIO CONSOLIDATION
// --------------------------------------------------

function consolidatePortfolios(allPortfolios) {

    const actualSnapshots = allPortfolios
        .filter(snapshot => !isDemoDocument(snapshot));

    const groups = new Map();

    for (const snapshot of actualSnapshots) {

        for (const holding of snapshot.holdings || []) {

            const key = getHoldingKey(holding, snapshot);

            if (!groups.has(key)) {
                groups.set(key, []);
            }

            groups.get(key).push({
                ...holding,
                documentId: snapshot.documentId,
                documentName: snapshot.documentName,
                documentType: snapshot.documentType,
                reportDate: snapshot.reportDate || null,
                snapshotCreatedAt: snapshot.createdAt,
                isDemo: false
            });
        }
    }

    const consolidatedHoldings = [];
    const duplicateRecords = [];
    const conflicts = [];

    for (const [key, records] of groups.entries()) {

        const datedRecords = records
            .filter(record =>
                record.reportDate &&
                !Number.isNaN(new Date(record.reportDate).getTime())
            )
            .sort((a, b) =>
                new Date(b.reportDate) - new Date(a.reportDate)
            );

        const distinctValues = [
            ...new Set(
                records
                    .map(record => record.currentValue)
                    .filter(isValidNumber)
            )
        ];

        const allRecordsHaveDates = records.every(
            record =>
                record.reportDate &&
                !Number.isNaN(new Date(record.reportDate).getTime())
        );

        const distinctReportDates = new Set(
            datedRecords.map(record =>
                new Date(record.reportDate).getTime()
            )
        );

        // Different values on different reliable statement dates:
        // use the latest statement date.
        //
        // Missing dates or same-date disagreements:
        // require verification.

        const hasConflict =
            distinctValues.length > 1 &&
            !(allRecordsHaveDates && distinctReportDates.size > 1);

        let selected;

        if (datedRecords.length > 0) {
            selected = datedRecords[0];
        } else {
            selected = records[0];
        }

        const consolidated = {
            ...selected,
            holdingKey: key,
            sourceDocuments: [
                ...new Set(
                    records
                        .map(record => record.documentName)
                        .filter(Boolean)
                )
            ],
            sourceRecordCount: records.length,
            hasConflict,
            conflictingValues: hasConflict ? distinctValues : []
        };

        consolidatedHoldings.push(consolidated);

        if (records.length > 1) {
            duplicateRecords.push({
                key,
                name: selected.name,
                selectedDocument: selected.documentName || null,
                records
            });
        }

        if (hasConflict) {
            conflicts.push({
                key,
                name: selected.name,
                values: distinctValues,
                selectedDocument: selected.documentName || null,
                message: allRecordsHaveDates
                    ? "Different values were reported for the same statement date. Verification is required."
                    : "Different values were found and at least one statement date is unavailable. Verification is required."
            });
        }
    }

    // Only verified current values enter analytics.

    const verifiedHoldings = consolidatedHoldings.filter(
        holding =>
            isValidNumber(holding.currentValue) &&
            holding.currentValue >= 0 &&
            !holding.hasConflict
    );

    const totalValue = verifiedHoldings.reduce(
        (sum, holding) => sum + holding.currentValue,
        0
    );

    const unverifiedHoldings = consolidatedHoldings.filter(
        holding =>
            !isValidNumber(holding.currentValue) ||
            holding.currentValue < 0 ||
            holding.hasConflict
    );

    const currency = actualSnapshots[0]?.currency || "INR";

    const reliableDates = actualSnapshots
        .map(snapshot => getSnapshotDate(snapshot))
        .filter(date => date.getTime() > 0)
        .sort((a, b) => b - a);

    return {
        portfolio: {
            clientId: actualSnapshots[0]?.clientId || null,
            currency,

            // Null means the complete portfolio value is not verified.
            totalValue: unverifiedHoldings.length === 0
                ? Number(totalValue.toFixed(2))
                : null,

            verifiedTotalValue: Number(totalValue.toFixed(2)),
            isPartial: unverifiedHoldings.length > 0,
            unverifiedHoldingCount: unverifiedHoldings.length,

            holdings: consolidatedHoldings,

            reportDate: reliableDates[0] || null,

            documentName: "Consolidated Portfolio",
            documentType: "consolidated",
            isDemo: false,

            sourceDocumentCount: actualSnapshots.length,
            holdingCount: consolidatedHoldings.length,
            verifiedHoldingCount: verifiedHoldings.length,
            conflictCount: conflicts.length
        },

        duplicateRecords,
        conflicts,
        actualSnapshots
    };
}


// --------------------------------------------------
// ANALYTICS PAYLOAD
// --------------------------------------------------

function createAnalyticsPayload(clientId, portfolio) {

    const holdings = (portfolio.holdings || [])
        .filter(holding =>
            isValidNumber(holding.currentValue) &&
            holding.currentValue >= 0 &&
            !holding.hasConflict
        )
        .map(item => ({
            name: item.name,
            asset_class: item.assetClass || "Other",
            sub_category: item.subCategory ?? null,
            isin: item.isin ?? null,
            folio_number: item.folioNumber ?? null,
            invested_value: item.investedValue ?? null,
            current_value: item.currentValue,
            quantity: item.quantity ?? null,
            page: item.page ?? null
        }));

    return {
        client_id: clientId,
        currency: portfolio.currency || "INR",
        holdings
    };
}


// --------------------------------------------------
// REGISTER
// --------------------------------------------------

app.post("/register", async (req, res) => {

    try {
        const { name, email, password } = req.body;

        if (!name || !email || !password || password.length < 8) {
            return res.status(400).send(
                "Enter valid details. Password must be at least 8 characters."
            );
        }

        const existingUser = await User.findOne({
            email: email.toLowerCase().trim()
        });

        if (existingUser) {
            return res.status(409).send("Email already registered.");
        }

        const hashedPassword = await bcrypt.hash(password, 12);

        const user = await User.create({
            name,
            email,
            password: hashedPassword,
            clientId: `CLIENT-${crypto.randomUUID()}`
        });

        req.session.user = {
            id: user._id,
            name: user.name,
            clientId: user.clientId
        };

        res.redirect("/");

    } catch (error) {
        console.error("Registration error:", error);
        res.status(500).send("Registration failed.");
    }
});


// --------------------------------------------------
// LOGIN
// --------------------------------------------------

app.post("/login", async (req, res) => {

    try {
        const { email, password } = req.body;

        const user = await User.findOne({
            email: email?.toLowerCase().trim()
        });

        if (!user || !(await bcrypt.compare(password || "", user.password))) {
            return res.status(401).send("Invalid email or password.");
        }

        req.session.user = {
            id: user._id,
            name: user.name,
            clientId: user.clientId
        };

        res.redirect("/");

    } catch (error) {
        console.error("Login error:", error);
        res.status(500).send("Login failed.");
    }
});


// --------------------------------------------------
// LOGOUT AND AUTHENTICATION
// --------------------------------------------------

app.post("/logout", (req, res) => {

    req.session.destroy(() => {
        res.clearCookie("connect.sid");
        res.redirect("/login");
    });
});

function requireAuth(req, res, next) {

    if (!req.session.user) {
        return res.redirect("/login");
    }

    next();
}

app.get("/login", (req, res) => {
    res.render("login");
});

app.get("/register", (req, res) => {
    res.render("register");
});

// --------------------------------------------------
// PROFILE SETTINGS
// --------------------------------------------------

app.get("/profile", requireAuth, async (req, res) => {
    try {
        const user = await User.findById(req.session.user.id).lean();

        if (!user) {
            return res.status(404).send("User not found.");
        }

        res.render("profile", {
            riskTolerance: user.riskTolerance || "",
            success: req.query.updated === "true"
        });

    } catch (error) {
        console.error("Profile loading error:", error);
        res.status(500).send("Unable to load profile settings.");
    }
});

app.post("/profile/risk-tolerance", requireAuth, async (req, res) => {
    try {
        const allowedValues = [
            "conservative",
            "moderate",
            "aggressive"
        ];

        const { riskTolerance } = req.body;

        if (!allowedValues.includes(riskTolerance)) {
            return res.status(400).send("Invalid risk tolerance.");
        }

        await User.findByIdAndUpdate(
            req.session.user.id,
            { riskTolerance },
            { runValidators: true }
        );

        res.redirect("/profile?updated=true");

    } catch (error) {
        console.error("Risk tolerance update error:", error);
        res.status(500).send("Unable to update risk tolerance.");
    }
});

// --------------------------------------------------
// DASHBOARD
// --------------------------------------------------

app.get("/", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;

        const allPortfolios = await Portfolio.find({ clientId })
            .sort({ reportDate: -1, createdAt: -1 })
            .lean();

        const allDocumentHoldings = allPortfolios.flatMap(snapshot =>
            (snapshot.holdings || []).map(holding => ({
                ...holding,
                documentName: snapshot.documentName || "Unknown document",
                documentType: snapshot.documentType || "Unknown",
                reportDate: snapshot.reportDate,
                isDemo: isDemoDocument(snapshot)
            }))
        );

        const consolidated = consolidatePortfolios(allPortfolios);
        const portfolio = consolidated.portfolio;

        if (portfolio.holdings.length === 0) {

            return res.render("dashboard", {
                portfolio: null,
                analytics: null,
                risk: null,
                allDocumentHoldings,
                duplicateRecords: [],
                conflicts: [],
                error: "No actual investment holdings found."
            });
        }

        const portfolioPayload = createAnalyticsPayload(
            clientId,
            portfolio
        );

        if (portfolioPayload.holdings.length === 0) {

            return res.render("dashboard", {
                portfolio,
                analytics: null,
                risk: null,
                allDocumentHoldings,
                duplicateRecords: consolidated.duplicateRecords,
                conflicts: consolidated.conflicts,
                error: "No holdings have verified current market values."
            });
        }

        const analyticsResponse = await axios.post(
            `${AI_URL}/analytics`,
            portfolioPayload,
            {
                headers: getServiceHeaders(),
                timeout: 30000
            }
        );

        const riskResponse = await axios.post(
            `${AI_URL}/risk`,
            portfolioPayload,
            {
                headers: getServiceHeaders(),
                timeout: 30000
            }
        );

        res.render("dashboard", {
            portfolio,
            analytics: analyticsResponse.data,
            risk: riskResponse.data,
            allDocumentHoldings,
            duplicateRecords: consolidated.duplicateRecords,
            conflicts: consolidated.conflicts,
            error: null
        });

    } catch (error) {

        console.error(
            "Dashboard error:",
            error.response?.data || error.message
        );

        res.render("dashboard", {
            portfolio: null,
            analytics: null,
            risk: null,
            allDocumentHoldings: [],
            duplicateRecords: [],
            conflicts: [],
            error: "Unable to load portfolio analytics."
        });
    }
});


 // --------------------------------------------------
 // HISTORICAL PORTFOLIO PERFORMANCE
 // --------------------------------------------------

app.get("/performance", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;

        // Fetch only this client's historical portfolio records.
        const portfolios = await Portfolio.find({ clientId })
            .sort({ reportDate: 1, createdAt: 1 })
            .lean();
            
        console.log("\n========== PERFORMANCE DEBUG ==========");
        console.log("Client ID:", clientId);
        console.log("Total portfolio records:", portfolios.length);

        console.log(
            "Demo records:",
            portfolios.filter(isDemoDocument).length
        );

        console.log(
            "Records without report date:",
            portfolios.filter(p => !p.reportDate).length
        );

        console.log(
            "Records with report date:",
            portfolios.filter(p => p.reportDate).length
        );

        console.log(
            "Report dates:",
            portfolios.map(p => p.reportDate)
        );

        console.log("=======================================\n");

        // Exclude demo records and records without reliable report dates.
        const validRecords = portfolios.filter(snapshot => {
            if (isDemoDocument(snapshot)) return false;
            if (!snapshot.reportDate) return false;

            const date = new Date(snapshot.reportDate);

            return !Number.isNaN(date.getTime());
        });

        // Group records by report date.
        const recordsByDate = new Map();

        for (const record of validRecords) {
            const dateKey = new Date(record.reportDate)
                .toISOString()
                .slice(0, 10);

            if (!recordsByDate.has(dateKey)) {
                recordsByDate.set(dateKey, []);
            }

            recordsByDate.get(dateKey).push(record);
        }

        const snapshots = [];
        const skippedDates = [];

        for (const [date, records] of recordsByDate.entries()) {

            // Multiple documents on the same date may overlap.
            if (records.length !== 1) {
                skippedDates.push({
                    report_date: date,
                    reason: "Multiple documents exist for this date."
                });
                continue;
            }

            const record = records[0];
            const holdings = record.holdings || [];

            // Do not treat missing values as zero.
            const hasCompleteValues =
                holdings.length > 0 &&
                holdings.every(holding =>
                    isValidNumber(holding.currentValue) &&
                    holding.currentValue >= 0
                );

            // A statement's explicitly reported total is sufficient for
            // portfolio-level history even when a few holding rows could
            // not be extracted. Older records without this marker must still
            // pass the complete-holdings check.
            const hasTrustedTotal =
                record.totalValueSource === "reported" ||
                (
                    record.totalValueSource !== "incomplete" &&
                    hasCompleteValues
                );

            if (!hasTrustedTotal) {
                skippedDates.push({
                    report_date: date,
                    reason: "No reliable reported portfolio total and holding values are incomplete."
                });
                continue;
            }

            if (
                !isValidNumber(record.totalValue) ||
                record.totalValue < 0
            ) {
                skippedDates.push({
                    report_date: date,
                    reason: "Invalid portfolio total."
                });
                continue;
            }

            snapshots.push({
                report_date: date,
                total_value: record.totalValue
            });
        }

        // Send historical snapshots to the Python engine.
        const response = await axios.post(
            `${AI_URL}/performance`,
            {
                client_id: clientId,
                snapshots
            },
            {
                headers: getServiceHeaders(),
                timeout: 30000
            }
        );

        return res.json({
            performance: response.data.performance,
            skipped_dates: skippedDates,
            source: "MongoDB Portfolio records"
        });

    } catch (error) {

        console.error(
            "Performance route error:",
            error.response?.data || error.message
        );

        return res.status(500).json({
            error: "Unable to calculate historical performance."
        });
    }
});

// --------------------------------------------------
// UPLOAD DOCUMENTS
// --------------------------------------------------

app.post(
    "/upload",
    requireAuth,
    upload.array("files", 10),
    async (req, res) => {

        const files = req.files || [];

        if (files.length === 0) {
            return res.status(400).send(
                "Please select at least one file."
            );
        }

        const clientId = req.session.user.clientId;
        const results = [];

        for (const file of files) {

            let documentRecord;

            try {

                const extension = path.extname(
                    file.originalname
                ).toLowerCase();

                if (![".pdf", ".xlsx"].includes(extension)) {
                    throw new Error(
                        "Only PDF and XLSX files are accepted."
                    );
                }

                const form = new FormData();

                form.append("client_id", clientId);

                form.append("file", file.buffer, {
                    filename: file.originalname,
                    contentType: file.mimetype
                });

                documentRecord = await Document.create({
                    clientId,
                    originalName: file.originalname,
                    storedName: file.originalname,
                    fileType: extension.replace(".", ""),
                    fileSize: file.size,
                    status: "processing"
                });
                form.append(
                    "document_id",
                    documentRecord._id.toString()
                );

                const response = await axios.post(
                    `${AI_URL}/upload`,
                    form,
                    {
                        headers: {
                            ...form.getHeaders(),
                            ...getServiceHeaders()
                        },
                        timeout: 120000,
                        maxBodyLength: Infinity
                    }
                );
                const storedFilename = response.data.stored_filename;

                if (!storedFilename) {
                    throw new Error("AI service did not return stored filename.");
                }

                await Document.findByIdAndUpdate(
                    documentRecord._id,
                    {
                        storedName: storedFilename
                    }
                );

                let holdings = [];
                let currency = "INR";
                let reportDate = null;
                let reportedTotalValue = null;

                // PDF PROCESSING

                if (extension === ".pdf") {

                    const extracted = response.data.portfolio;

                    if (
                        !extracted ||
                        !Array.isArray(extracted.holdings) ||
                        extracted.holdings.length === 0
                    ) {
                        throw new Error(
                            "Invalid portfolio data extracted from PDF."
                        );
                    }

                    holdings = extracted.holdings.map(item => ({
                        name: item.name,
                        assetClass: item.asset_class || "Other",
                        subCategory: item.sub_category ?? null,
                        isin: item.isin ?? null,
                        quantity: item.quantity ?? null,
                        investedValue: item.invested_value ?? null,
                        currentValue: item.current_value ?? null,
                        profitLoss: item.profit_loss ?? null,
                        profitLossPercentage:
                            item.profit_loss_percentage ?? null,
                        folioNumber: item.folio_number ?? null,
                        source: item.source ?? null,
                        averageNav: item.average_nav ?? null,
                        currentNav: item.current_nav ?? null,
                        page: item.page ?? null
                    }));

                    currency = extracted.currency || "INR";

                    if (
                        extracted.report_date &&
                        !Number.isNaN(
                            new Date(extracted.report_date).getTime()
                        )
                    ) {
                        reportDate = new Date(extracted.report_date);
                    }

                    // Prefer the explicitly reported statement total.
                    // Never derive historical portfolio value from a partial
                    // set of extracted holdings.
                    if (
                        isValidNumber(extracted.total_value) &&
                        extracted.total_value >= 0
                    ) {
                        reportedTotalValue = extracted.total_value;
                    }

                    for (const item of holdings) {

                        if (
                            typeof item.name !== "string" ||
                            !item.name.trim() ||
                            (
                                item.currentValue !== null &&
                                item.currentValue !== undefined &&
                                (
                                    !isValidNumber(item.currentValue) ||
                                    item.currentValue < 0
                                )
                            )
                        ) {
                            throw new Error(
                                `Invalid PDF holding: ${item.name || "Unknown"}`
                            );
                        }
                    }
                }

                // EXCEL PROCESSING

                else if (extension === ".xlsx") {

                    const sheets = response.data.sheets;
                    console.log("EXCEL API RESPONSE:");
                    console.dir(response.data, { depth: 6 });

                    console.log("SHEET NAMES:", Object.keys(sheets || {}));

                    for (const [name, sheet] of Object.entries(sheets || {})) {
                        console.log("SHEET:", name);
                        console.log("STATUS:", sheet?.status);
                        console.log("HOLDINGS COUNT:", sheet?.holdings?.length);
                    }
                    if (
                        response.data.report_date &&
                        !Number.isNaN(new Date(response.data.report_date).getTime())
                    ) {
                        reportDate = new Date(response.data.report_date);
                    }

                    if (!sheets || typeof sheets !== "object") {
                        throw new Error(
                            "Invalid Excel extraction response."
                        );
                    }

                    for (const sheet of Object.values(sheets)) {

                        if (
                            sheet.status !== "processed" ||
                            !Array.isArray(sheet.holdings)
                        ) {
                            continue;
                        }

                        for (const item of sheet.holdings) {

                            const holding = {
                                name: item.name,
                                assetClass: item.asset_class || "Other",
                                subCategory: item.sub_category ?? null,
                                isin: item.isin ?? null,
                                quantity: item.quantity ?? null,
                                investedValue: item.invested_value ?? null,
                                currentValue: item.current_value ?? null,
                                profitLoss: item.profit_loss ?? null,
                                profitLossPercentage:
                                    item.profit_loss_percentage ?? null,
                                folioNumber: item.folio_number ?? null,
                                source: item.source ?? null,
                                averageNav: item.average_nav ?? null,
                                currentNav: item.current_nav ?? null,
                                rowNumber: item.row_number ?? null,
                                page: null
                            };

                            if (
                                typeof holding.name !== "string" ||
                                !holding.name.trim()
                            ) {
                                continue;
                            }

                            holdings.push(holding);
                        }
                    }

                    if (holdings.length === 0) {
                        throw new Error(
                            "No investment records found in Excel."
                        );
                    }
                }

                // VALIDATE FINANCIAL VALUES

                for (const holding of holdings) {

                    for (const field of [
                        "currentValue",
                        "investedValue",
                        "quantity",
                        "profitLoss",
                        "profitLossPercentage",
                        "averageNav",
                        "currentNav"
                    ]) {

                        const value = holding[field];

                        if (
                            value !== null &&
                            value !== undefined &&
                            !isValidNumber(value)
                        ) {
                            throw new Error(
                                `Invalid ${field} for ${holding.name}.`
                            );
                        }
                    }

                    if (
                        holding.currentValue !== null &&
                        holding.currentValue < 0
                    ) {
                        throw new Error(
                            `Negative current value for ${holding.name}.`
                        );
                    }

                    if (
                        holding.investedValue !== null &&
                        holding.investedValue < 0
                    ) {
                        throw new Error(
                            `Negative invested value for ${holding.name}.`
                        );
                    }
                }

                // Determine whether the snapshot has a trustworthy total.
                // A printed statement total is preferred. Otherwise calculate
                // only when every extracted holding has a valid current value.
                const allHoldingsHaveCurrentValues =
                    holdings.length > 0 &&
                    holdings.every(item =>
                        isValidNumber(item.currentValue) &&
                        item.currentValue >= 0
                    );

                const calculatedTotal = allHoldingsHaveCurrentValues
                    ? holdings.reduce(
                        (sum, item) => sum + item.currentValue,
                        0
                    )
                    : null;

                const totalValueSource = isValidNumber(reportedTotalValue)
                    ? "reported"
                    : allHoldingsHaveCurrentValues
                        ? "holdings"
                        : "incomplete";

                const snapshotTotal = totalValueSource === "reported"
                    ? reportedTotalValue
                    : totalValueSource === "holdings"
                        ? calculatedTotal
                        : holdings.reduce(
                            (sum, item) =>
                                sum + (
                                    isValidNumber(item.currentValue)
                                        ? item.currentValue
                                        : 0
                                ),
                            0
                        );

                const isDemo = /demo|sample|illustrative/i.test(
                    file.originalname
                );

                await Portfolio.create({
                    clientId,
                    documentId: documentRecord._id,
                    documentName: file.originalname,
                    documentType: extension.replace(".", ""),
                    isDemo,
                    currency,
                    totalValue: Number(snapshotTotal.toFixed(2)),
                    totalValueSource,
                    reportDate,
                    holdings
                });

                console.log(
                    "Portfolio snapshot saved:",
                    file.originalname,
                    "Records:",
                    holdings.length,
                    "Total:",
                    calculatedTotal,
                    "Demo:",
                    isDemo
                );

                await Document.findByIdAndUpdate(
                    documentRecord._id,
                    {
                        totalChunks: response.data.total_chunks || 0,
                        status: "ready"
                    }
                );

                results.push({
                    filename: file.originalname,
                    status: "ready"
                });

            } catch (error) {

                console.error(
                    `Upload failed for ${file.originalname}:`,
                    error.response?.data || error.message
                );

                if (documentRecord) {
                    await Document.findByIdAndUpdate(
                        documentRecord._id,
                        { status: "failed" }
                    );
                }

                results.push({
                    filename: file.originalname,
                    status: "failed",
                    error: error.message
                });
            }
        }

        const successful = results.filter(
            item => item.status === "ready"
        ).length;

        if (successful === 0) {
            return res.status(500).send(
                "All document uploads failed. Please check the server logs."
            );
        }

        console.log("Upload results:", results);

        res.redirect("/");
    }
);

// --------------------------------------------------
// CHAT
// --------------------------------------------------

app.post("/chat", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;
        const question = req.body.question?.trim();

        if (!question) {
            return res.status(400).json({
                error: "Please enter a question."
            });
        }

        const response = await axios.post(
            `${AI_URL}/chat`,
            {
                question,
                client_id: clientId
            },
            {
                headers: getServiceHeaders()
            }
        );

        const result = response.data;

        let chat = await Chat.findOne({ clientId });

        if (!chat) {
            chat = new Chat({
                clientId,
                messages: []
            });
        }

        chat.messages.push({
            role: "user",
            content: question
        });

        chat.messages.push({
            role: "assistant",
            content: result.answer,
            sources: (result.sources || []).map(source => ({
                source: source.source || source.filename || "Uploaded document",
                page: source.page,
                similarity: source.similarity
            }))
        });

        await chat.save();

        res.json(result);

    } catch (error) {

        console.error("Chat error:", error.message);

        res.status(500).json({
            error: "Unable to process chat request."
        });
    }
});


// --------------------------------------------------
// CHAT HISTORY
// --------------------------------------------------

app.get("/chat/history", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;

        const chat = await Chat.findOne({ clientId });

        res.json({
            messages: chat ? chat.messages : []
        });

    } catch (error) {

        console.error("Chat history error:", error.message);

        res.status(500).json({
            error: "Unable to load chat history."
        });
    }
});


// --------------------------------------------------
// RISK EXPLANATION
// --------------------------------------------------

app.post("/risk/explanation", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;

        const allPortfolios = await Portfolio.find({ clientId })
            .sort({ reportDate: -1, createdAt: -1 })
            .lean();

        const consolidated = consolidatePortfolios(allPortfolios);

        if (consolidated.portfolio.holdings.length === 0) {
            return res.status(404).json({
                error: "Portfolio not found."
            });
        }

        const portfolioPayload = createAnalyticsPayload(
            clientId,
            consolidated.portfolio
        );

        if (portfolioPayload.holdings.length === 0) {
            return res.status(409).json({
                error: "No verified holdings are available for risk analysis."
            });
        }

        const response = await axios.post(
            `${AI_URL}/risk/explanation`,
            portfolioPayload,
            {
                headers: getServiceHeaders()
            }
        );

        res.json(response.data);

    } catch (error) {

        console.error(
            "Risk explanation error:",
            error.response?.data || error.message
        );

        res.status(500).json({
            error: "Unable to generate AI risk explanation."
        });
    }
});


// --------------------------------------------------
// LEGACY PORTFOLIO SYNC
// --------------------------------------------------

app.post("/portfolio/sync", requireAuth, async (req, res) => {

    try {
        const filePath = path.join(
            __dirname,
            "../data/portfolio.json"
        );

        const portfolioData = JSON.parse(
            fs.readFileSync(filePath, "utf8")
        );

        const clientId = req.session.user.clientId;

        const holdings = portfolioData.holdings.map(item => ({
            name: item.name,
            assetClass: item.asset_class || "Other",
            investedValue: item.invested_value ?? null,
            currentValue: item.value ?? null,
            page: item.page ?? null
        }));

        const validTotal = holdings.reduce(
            (sum, item) =>
                sum + (
                    isValidNumber(item.currentValue)
                        ? item.currentValue
                        : 0
                ),
            0
        );

        const portfolio = await Portfolio.create({
            clientId,
            currency: portfolioData.currency || "INR",
            totalValue: validTotal,
            reportDate: portfolioData.report_date || new Date(),
            holdings,
            isDemo: false
        });

        res.json({
            message: "Portfolio saved successfully!",
            portfolio
        });

    } catch (error) {

        console.error("Portfolio sync error:", error.message);

        res.status(500).json({
            error: "Unable to save portfolio."
        });
    }
});


// --------------------------------------------------
// DOCUMENT LIST
// --------------------------------------------------
// --------------------------------------------------
// DELETE DOCUMENT
// --------------------------------------------------

app.delete("/documents/:id", requireAuth, async (req, res) => {

    try {
        const clientId = req.session.user.clientId;
        const documentId = req.params.id;

        if (!/^[a-fA-F0-9]{24}$/.test(documentId)) {
            return res.status(400).json({
                error: "Invalid document ID."
            });
        }

        // 1. Verify ownership
        const document = await Document.findOne({
            _id: documentId,
            clientId
        });
        console.log("STORED FILENAME:", document?.storedName);

        if (!document) {
            return res.status(404).json({
                error: "Document not found."
            });
        }

        if (!document.storedName) {
            return res.status(409).json({
                error: "Stored filename is missing."
            });
        }

        // 2. Delete original file and FAISS chunks
        
        await axios.delete(
            `${AI_URL}/documents/${documentId}`,
            {
                headers: getServiceHeaders(),
                params: {
                    client_id: clientId,
                    stored_filename: document.storedName
                },
                timeout: 60000
            }
        );
        // 3. Delete associated portfolio records
        await Portfolio.deleteMany({
            clientId,
            documentId: document._id
        });

        // 4. Delete MongoDB document metadata
        await Document.deleteOne({
            _id: document._id,
            clientId
        });

        return res.json({
            message: "Document deleted successfully."
        });

    } catch (error) {
        console.error(
            "Document deletion error:",
             JSON.stringify(error.response?.data || error.message, null, 2)
        );

        return res.status(500).json({
            error: "Unable to delete document."
        });
    }
});

app.get("/documents", requireAuth, async (req, res) => {

    try {
        const documents = await Document.find({
            clientId: req.session.user.clientId
        })
        .sort({ createdAt: -1 })
        .lean();

        res.json({
            documents: documents.map(doc => ({
                id: doc._id.toString(),
                name: doc.originalName,
                type: (doc.fileType || "unknown").toUpperCase(),
                size: doc.fileSize,
                chunks: doc.totalChunks,
                status: doc.status,
                uploadedAt: doc.createdAt
            }))
        });

    } catch (error) {

        console.error("Document listing error:", error.message);

        res.status(500).json({
            error: "Unable to load documents."
        });
    }
});

//Financial Goal

// --------------------------------------------------
// FINANCIAL GOALS API
// --------------------------------------------------

const allowedGoalFields = [
    "name",
    "category",
    "targetAmount",
    "currentSavings",
    "targetDate",
    "inflationRate",
    "expectedAnnualReturn",
    "monthlyContribution",
    "status"
];

function validateGoalInput(data, isUpdate = false) {

    const errors = [];

    if (!isUpdate || data.name !== undefined) {
        if (
            typeof data.name !== "string" ||
            !data.name.trim()
        ) {
            errors.push("Goal name is required.");
        }
    }

    if (!isUpdate || data.category !== undefined) {
        const categories = [
            "Retirement",
            "House",
            "Education",
            "Travel",
            "Vehicle",
            "Medical",
            "Wedding",
            "Business",
            "Emergency Fund",
            "Other"
        ];

        if (!categories.includes(data.category)) {
            errors.push("Invalid goal category.");
        }
    }

    const numericFields = [
        "targetAmount",
        "currentSavings",
        "inflationRate",
        "expectedAnnualReturn",
        "monthlyContribution"
    ];

    for (const field of numericFields) {

        if (data[field] === undefined) {
            if (!isUpdate && field === "targetAmount") {
                errors.push("Target amount is required.");
            }
            continue;
        }

        const value = data[field];

        if (
            typeof value !== "number" ||
            !Number.isFinite(value) ||
            value < 0
        ) {
            errors.push(`${field} must be a valid non-negative number.`);
        }
    }

    if (data.targetAmount !== undefined && data.targetAmount <= 0) {
        errors.push("Target amount must be greater than zero.");
    }

    if (
        data.inflationRate !== undefined &&
        data.inflationRate > 30
    ) {
        errors.push("Inflation rate cannot exceed 30%.");
    }

    if (
        data.expectedAnnualReturn !== undefined &&
        data.expectedAnnualReturn > 50
    ) {
        errors.push("Expected return cannot exceed 50%.");
    }

    if (data.targetDate !== undefined) {

        const date = new Date(data.targetDate);

        if (Number.isNaN(date.getTime())) {
            errors.push("Invalid target date.");
        } else if (date <= new Date()) {
            errors.push("Target date must be in the future.");
        }
    }

    if (
        data.status !== undefined &&
        !["Active", "Completed", "Paused"].includes(data.status)
    ) {
        errors.push("Invalid goal status.");
    }

    return errors;
}


// GET ALL GOALS

app.get("/goals", requireAuth, async (req, res) => {

    try {

        const clientId = req.session.user.clientId;

        const goals = await FinancialGoal.find({ clientId })
            .sort({ targetDate: 1 })
            .lean();

        const result = goals.map(goal => ({
            ...goal,
            plan: calculateGoalPlan(goal)
        }));

        return res.json({ goals: result });

    } catch (error) {

        console.error("Goal listing error:", error.message);

        return res.status(500).json({
            error: "Unable to load financial goals."
        });
    }
});


// CREATE GOAL

app.post("/goals", requireAuth, async (req, res) => {

    try {

        const errors = validateGoalInput(req.body);

        if (errors.length > 0) {
            return res.status(400).json({ errors });
        }

        const goalData = {};

        for (const field of allowedGoalFields) {
            if (req.body[field] !== undefined) {
                goalData[field] = req.body[field];
            }
        }

        const goal = await FinancialGoal.create({
            ...goalData,
            clientId: req.session.user.clientId
        });

        return res.status(201).json({
            message: "Financial goal created successfully.",
            goal: {
                ...goal.toObject(),
                plan: calculateGoalPlan(goal.toObject())
            }
        });

    } catch (error) {

        console.error("Goal creation error:", error.message);

        return res.status(500).json({
            error: "Unable to create financial goal."
        });
    }
});


// UPDATE GOAL

app.put("/goals/:id", requireAuth, async (req, res) => {

    try {

        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({
                error: "Invalid goal ID."
            });
        }

        const errors = validateGoalInput(req.body, true);

        if (errors.length > 0) {
            return res.status(400).json({ errors });
        }

        const updateData = {};

        for (const field of allowedGoalFields) {
            if (req.body[field] !== undefined) {
                updateData[field] = req.body[field];
            }
        }

        const goal = await FinancialGoal.findOneAndUpdate(
            {
                _id: req.params.id,
                clientId: req.session.user.clientId
            },
            { $set: updateData },
            {
                new: true,
                runValidators: true
            }
        );

        if (!goal) {
            return res.status(404).json({
                error: "Financial goal not found."
            });
        }
        // Fetch the user's saved investment risk preference
        const assessmentUser = await User.findById(
            req.session.user.id
        ).select("riskTolerance").lean();

        if (!assessmentUser?.riskTolerance) {
            return res.status(422).json({
                error: "Please select your risk tolerance in Profile Settings before generating a personalized goal assessment."
            });
        }

        return res.json({
            message: "Financial goal updated successfully.",
            goal: {
                ...goal.toObject(),
                plan: calculateGoalPlan(goal.toObject())
            }
        });

    } catch (error) {

        console.error("Goal update error:", error.message);

        return res.status(500).json({
            error: "Unable to update financial goal."
        });
    }
});


// --------------------------------------------------
// GET HOLDINGS AVAILABLE FOR A GOAL
// --------------------------------------------------

app.get("/goals/:id/holdings", requireAuth, async (req, res) => {
    try {
        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({
                error: "Invalid goal ID."
            });
        }

        const clientId = req.session.user.clientId;

        const goal = await FinancialGoal.findOne({
            _id: req.params.id,
            clientId
        }).lean();

        if (!goal) {
            return res.status(404).json({
                error: "Goal not found."
            });
        }

        const snapshots = await Portfolio.find({ clientId }).lean();
        const consolidated = consolidatePortfolios(snapshots);

        const verifiedHoldings = consolidated.portfolio.holdings.filter(
            holding =>
                typeof holding.currentValue === "number" &&
                Number.isFinite(holding.currentValue) &&
                holding.currentValue >= 0 &&
                !holding.hasConflict
        );

        const allocations = await GoalHoldingAllocation.find({
            clientId
        }).lean();

        const result = verifiedHoldings.map(holding => {
            const holdingAllocations = allocations.filter(
                allocation =>
                    allocation.holdingKey === holding.holdingKey
            );

            const thisGoalAllocation = holdingAllocations
                .filter(
                    allocation =>
                        String(allocation.goalId) === String(goal._id)
                )
                .reduce((sum, item) => sum + item.amount, 0);

            const otherGoalsAllocation = holdingAllocations
                .filter(
                    allocation =>
                        String(allocation.goalId) !== String(goal._id)
                )
                .reduce((sum, item) => sum + item.amount, 0);

            // Subtract allocations to ALL goals.
            const availableAmount = Math.max(
                0,
                holding.currentValue -
                thisGoalAllocation -
                otherGoalsAllocation
            );
            console.log({
            holding: holding.name,
            currentValue: holding.currentValue,
            thisGoalAllocation,
            otherGoalsAllocation
        });

            return {
                holdingKey: holding.holdingKey,
                name: holding.name,
                assetClass: holding.assetClass,
                subCategory: holding.subCategory,
                isin: holding.isin,
                currentValue: holding.currentValue,
                allocatedToThisGoal: Number(
                    thisGoalAllocation.toFixed(2)
                ),
                allocatedToOtherGoals: Number(
                    otherGoalsAllocation.toFixed(2)
                ),
                availableAmount: Number(
                    availableAmount.toFixed(2)
                )
            };
        });

        const totalAllocatedToThisGoal = result.reduce(
            (sum, holding) => sum + holding.allocatedToThisGoal,
            0
        );

        return res.json({
            goal: {
                id: goal._id,
                name: goal.name
            },
            holdings: result,
            totalAllocatedToThisGoal: Number(
                totalAllocatedToThisGoal.toFixed(2)
            )
        });

    } catch (error) {
        console.error("Goal holdings error:", error);

        return res.status(500).json({
            error: "Unable to load available holdings."
        });
    }
});


// --------------------------------------------------
// SAVE HOLDING ALLOCATIONS FOR A GOAL
// --------------------------------------------------

app.put("/goals/:id/allocations", requireAuth, async (req, res) => {
    const session = await mongoose.startSession();

    try {
        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({ error: "Invalid goal ID." });
        }

        const { allocations } = req.body;

        if (!Array.isArray(allocations)) {
            return res.status(400).json({
                error: "allocations must be an array."
            });
        }

        const seenKeys = new Set();

        for (const item of allocations) {
            if (
                !item ||
                typeof item.holdingKey !== "string" ||
                !item.holdingKey.trim() ||
                typeof item.amount !== "number" ||
                !Number.isFinite(item.amount) ||
                item.amount <= 0
            ) {
                return res.status(400).json({
                    error: "Each allocation needs a valid holdingKey and positive amount."
                });
            }

            if (seenKeys.has(item.holdingKey)) {
                return res.status(400).json({
                    error: "A holding can appear only once in this request."
                });
            }

            seenKeys.add(item.holdingKey);
        }

        const clientId = req.session.user.clientId;
        let responseData;

        await session.withTransaction(async () => {

            const goal = await FinancialGoal.findOne({
                _id: req.params.id,
                clientId
            }).session(session);

            if (!goal) {
                throw new Error("GOAL_NOT_FOUND");
            }

            const snapshots = await Portfolio.find({ clientId })
                .session(session)
                .lean();

            const consolidated = consolidatePortfolios(snapshots);

            const verifiedHoldings = consolidated.portfolio.holdings.filter(
                holding =>
                    typeof holding.currentValue === "number" &&
                    Number.isFinite(holding.currentValue) &&
                    holding.currentValue >= 0 &&
                    !holding.hasConflict
            );

            const holdingMap = new Map(
                verifiedHoldings.map(holding => [
                    holding.holdingKey,
                    holding
                ])
            );

            const otherAllocations = await GoalHoldingAllocation.find({
                clientId,
                goalId: { $ne: goal._id }
            }).session(session).lean();

            const otherTotals = new Map();

            for (const allocation of otherAllocations) {
                const previous = otherTotals.get(allocation.holdingKey) || 0;

                otherTotals.set(
                    allocation.holdingKey,
                    previous + allocation.amount
                );
            }

            const newAllocationDocuments = [];
            let totalAllocated = 0;

            for (const item of allocations) {
                const holding = holdingMap.get(item.holdingKey);

                if (!holding) {
                    throw new Error("HOLDING_NOT_AVAILABLE");
                }

                const alreadyAllocated =
                    otherTotals.get(item.holdingKey) || 0;

                const availableAmount =
                    holding.currentValue - alreadyAllocated;

                if (item.amount > availableAmount + 0.001) {
                    throw new Error(
                        `ALLOCATION_EXCEEDS_AVAILABLE:${holding.name}:${Math.max(0, availableAmount).toFixed(2)}`
                    );
                }

                newAllocationDocuments.push({
                    clientId,
                    goalId: goal._id,
                    holdingKey: holding.holdingKey,
                    holdingName: holding.name,
                    amount: Number(item.amount.toFixed(2)),
                    currency: consolidated.portfolio.currency || "INR"
                });

                totalAllocated += item.amount;
            }

            await GoalHoldingAllocation.deleteMany({
                clientId,
                goalId: goal._id
            }).session(session);

            if (newAllocationDocuments.length > 0) {
                await GoalHoldingAllocation.insertMany(
                    newAllocationDocuments,
                    { session }
                );
            }

            goal.portfolioAllocatedAmount = Number(
                totalAllocated.toFixed(2)
            );

            await goal.save({ session });

            responseData = {
                message: "Goal allocations saved successfully.",
                goalId: goal._id,
                portfolioAllocatedAmount: goal.portfolioAllocatedAmount,
                allocationCount: newAllocationDocuments.length
            };
        });

        return res.json(responseData);

    } catch (error) {
        console.error("Goal allocation error:", error);

        if (error.message === "GOAL_NOT_FOUND") {
            return res.status(404).json({ error: "Goal not found." });
        }

        if (error.message === "HOLDING_NOT_AVAILABLE") {
            return res.status(400).json({
                error: "A selected holding is not currently verified in the portfolio."
            });
        }

        if (error.message.startsWith("ALLOCATION_EXCEEDS_AVAILABLE:")) {
            const details = error.message.split(":");

            return res.status(400).json({
                error: `${details[1]} has only ₹${details[2]} available for this goal.`
            });
        }

        return res.status(500).json({
            error: "Unable to save goal allocations."
        });

    } finally {
        await session.endSession();
    }
});


// DELETE GOAL


app.delete("/goals/:id", requireAuth, async (req, res) => {

    try {

        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({
                error: "Invalid goal ID."
            });
        }

        const clientId = req.session.user.clientId;

        // Find the goal first
        const goal = await FinancialGoal.findOne({
            _id: req.params.id,
            clientId
        });

        if (!goal) {
            return res.status(404).json({
                error: "Financial goal not found."
            });
        }

        // Delete all holding allocations linked to this goal
        await GoalHoldingAllocation.deleteMany({
            clientId,
            goalId: goal._id
        });

        // Delete the financial goal
        await FinancialGoal.deleteOne({
            _id: goal._id,
            clientId
        });

        return res.json({
            message: "Financial goal and its holding allocations deleted successfully."
        });

    } catch (error) {

        console.error("Goal deletion error:", error);

        return res.status(500).json({
            error: "Unable to delete financial goal."
        });
    }
});


app.get("/financial-goals", requireAuth, (req, res) => {
    res.render("financial-goals");
});


//calc
// --------------------------------------------------
// GOAL-BASED PORTFOLIO ASSESSMENT
// --------------------------------------------------


app.get("/goals/:id/assessment", requireAuth, async (req, res) => {
    try {
        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({
                error: "Invalid goal ID."
            });
        }

        const clientId = req.session.user.clientId;

        // 1. Fetch this client's goal
        const goal = await FinancialGoal.findOne({
            _id: req.params.id,
            clientId
        }).lean();

        if (!goal) {
            return res.status(404).json({
                error: "Financial goal not found."
            });
        }
        const assessmentUser = await User.findById(
            req.session.user.id
        ).select("riskTolerance").lean();

        if (!assessmentUser?.riskTolerance) {
            return res.status(422).json({
                error: "Please select your risk tolerance in Profile Settings before generating a personalized goal assessment."
            });
        }

        // 2. Load and consolidate portfolio snapshots
        const allPortfolios = await Portfolio.find({ clientId })
            .sort({ reportDate: -1, createdAt: -1 })
            .lean();

        const consolidated = consolidatePortfolios(allPortfolios);
        const portfolio = consolidated.portfolio;

        if (!portfolio.holdings.length) {
            return res.status(404).json({
                error: "No actual portfolio holdings found."
            });
        }

        // 3. Fetch allocations belonging ONLY to this goal
        const allocations = await GoalHoldingAllocation.find({
            clientId,
            goalId: goal._id
        }).lean();

        if (!allocations.length) {
            return res.status(422).json({
                error: "No holdings have been allocated to this goal."
            });
        }

        // 4. Match allocations against verified consolidated holdings
        const holdingMap = new Map(
            portfolio.holdings
                .filter(holding =>
                    isValidNumber(holding.currentValue) &&
                    holding.currentValue > 0 &&
                    !holding.hasConflict
                )
                .map(holding => [holding.holdingKey, holding])
        );

        const allocatedHoldings = [];

        for (const allocation of allocations) {
            const holding = holdingMap.get(allocation.holdingKey);

            if (!holding) {
                return res.status(422).json({
                    error: `Allocated holding "${allocation.holdingName}" is no longer verified.`
                });
            }

            if (
                !isValidNumber(allocation.amount) ||
                allocation.amount <= 0 ||
                allocation.amount > holding.currentValue + 0.001
            ) {
                return res.status(422).json({
                    error: `Invalid allocation for "${holding.name}".`
                });
            }

            // Scale cost basis and quantity proportionally.
            const allocationRatio =
                allocation.amount / holding.currentValue;

            allocatedHoldings.push({
                ...holding,
                currentValue: allocation.amount,
                investedValue:
                    isValidNumber(holding.investedValue)
                        ? holding.investedValue * allocationRatio
                        : null,
                quantity:
                    isValidNumber(holding.quantity)
                        ? holding.quantity * allocationRatio
                        : null
            });
        }

        // 5. Build a risk payload containing ONLY goal allocations
        const goalPortfolioPayload = createAnalyticsPayload(
            clientId,
            {
                ...portfolio,
                holdings: allocatedHoldings
            }
        );

        if (!goalPortfolioPayload.holdings.length) {
            return res.status(422).json({
                error: "No valid allocated holdings are available."
            });
        }
        const targetDate = new Date(goal.targetDate);

        const horizonYears = Number.isNaN(targetDate.getTime())
            ? null
            : Math.max(
                0,
                (targetDate.getTime() - Date.now()) /
                (365.25 * 24 * 60 * 60 * 1000)
            );

        goalPortfolioPayload.profile = {
            risk_tolerance: assessmentUser.riskTolerance,
            goal: goal.category,
            horizon_years: horizonYears
        };

        // 6. Call the dedicated goal risk endpoint
        const riskResponse = await axios.post(
            `${AI_URL}/risk/goal`,
            goalPortfolioPayload,
            {
                headers: getServiceHeaders(),
                timeout: 30000
            }
        );

        const riskData = riskResponse.data;

        // 7. Calculate funding assessment
        const assessment = calculateGoalAssessment(
            goal,
            riskData.risk_flags || []
        );

        // 8. Return goal-specific risk and funding context
        return res.json({
            assessment,

            portfolio_context: {
                goal_allocated_value: riskData.total_value,
                verified_total_value: portfolio.verifiedTotalValue,
                is_partial: portfolio.isPartial,
                risk_profile: riskData.profile_used,
                risk_thresholds: riskData.thresholds,
                goal_holding_count: riskData.holding_count,
                verified_holding_count: portfolio.verifiedHoldingCount,
                unverified_holding_count: portfolio.unverifiedHoldingCount,
                report_date: portfolio.reportDate,
                asset_allocation: riskData.asset_allocation,
                equity_percentage: riskData.equity_percentage,
                concentration: riskData.concentration,
                liquidity: riskData.liquidity,
                risk_flags: riskData.risk_flags
            },

            data_note:
                "Risk analysis uses only verified holdings allocated to this goal. Cost basis and quantity are proportionally estimated from the allocation amount."
        });

    } catch (error) {
        console.error(
            "Goal assessment error:",
            error.response?.data || error.message
        );

        return res.status(500).json({
            error: "Unable to generate goal-based portfolio assessment."
        });
    }
});

app.get("/financial-goals", requireAuth, (req, res) => {
    res.render("financial-goals");
});
app.get("/financial-goals/:id/assessment", requireAuth, (req, res) => {
    res.render("goal-assessment", {
        goalId: req.params.id
    });
});

// --------------------------------------------------
// START SERVER
// --------------------------------------------------

connectDB()
    .then(() => {

        sessionMiddleware = session({
            secret: process.env.SESSION_SECRET,
            resave: false,
            saveUninitialized: false,
            store: MongoStore.create({
                client: mongoose.connection.getClient(),
                touchAfter: 24 * 60 * 60
            }),
            cookie: {
                httpOnly: true,
                secure: false,
                sameSite: "lax",
                maxAge: 1000 * 60 * 60 * 24
            }
        });

        app.listen(PORT, () => {
            console.log(
                `WealthWise AI running at http://localhost:${PORT}`
            );
        });

    })
    .catch(error => {
        console.error("Database connection failed:", error);
    });
