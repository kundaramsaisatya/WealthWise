
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

    // Same security in the same folio.
    if (isin && folio) {
        return `ISIN:${isin}|FOLIO:${folio}`;
    }

    // Conservative fallback when ISIN is unavailable.
    if (folio && name) {
        return `FOLIO:${folio}|NAME:${name}`;
    }

    // Never merge using ISIN alone or name alone.
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

            if (!hasCompleteValues) {
                skippedDates.push({
                    report_date: date,
                    reason: "Some holdings have missing or invalid current values."
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

                // CALCULATE TOTAL USING AVAILABLE VALUES

                const calculatedTotal = holdings.reduce(
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
                    totalValue: Number(calculatedTotal.toFixed(2)),
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


// DELETE GOAL

app.delete("/goals/:id", requireAuth, async (req, res) => {

    try {

        if (!mongoose.Types.ObjectId.isValid(req.params.id)) {
            return res.status(400).json({
                error: "Invalid goal ID."
            });
        }

        const goal = await FinancialGoal.findOneAndDelete({
            _id: req.params.id,
            clientId: req.session.user.clientId
        });

        if (!goal) {
            return res.status(404).json({
                error: "Financial goal not found."
            });
        }

        return res.json({
            message: "Financial goal deleted successfully."
        });

    } catch (error) {

        console.error("Goal deletion error:", error.message);

        return res.status(500).json({
            error: "Unable to delete financial goal."
        });
    }
});

app.get("/financial-goals", requireAuth, (req, res) => {
    res.render("financial-goals");
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
