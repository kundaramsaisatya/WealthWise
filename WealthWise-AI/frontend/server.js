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

const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 10 * 1024 * 1024 }
});

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, "public")));



// REGISTER
app.post("/register", async (req, res) => {
    try {
        const { name, email, password } = req.body;

        if (!name || !email || !password || password.length < 8) {
            return res.status(400).send("Enter valid details. Password must be at least 8 characters.");
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


// LOGIN
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


// LOGOUT
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
app.get("/", requireAuth, async (req, res) => {
    try {
        const clientId = req.session.user.clientId;

        // Fetch this user's portfolio from MongoDB
        const portfolio = await Portfolio.findOne({ clientId }).lean();

        if (!portfolio) {
            return res.render("dashboard", {
                analytics: null,
                risk: null,
                error: "No portfolio found. Please sync your portfolio."
            });
        }

        // Prepare portfolio data for Python
        const portfolioPayload = {
            client_id: clientId,
            currency: portfolio.currency,
            holdings: portfolio.holdings.map(item => ({
                name: item.name,
                asset_class: item.assetClass,
                value: item.value,
                page: item.page
            }))
        };

        const headers = {
            "X-Service-Secret": process.env.AI_SERVICE_SECRET
        };

        // Send portfolio to Python analytics
        const analyticsResponse = await axios.post(
            `${AI_URL}/analytics`,
            portfolioPayload,
            { headers }
        );

        // Risk endpoint will be updated to accept portfolio data next
        const riskResponse = await axios.post(
            `${AI_URL}/risk`,
            portfolioPayload,
            { headers }
        );

        res.render("dashboard", {
            analytics: analyticsResponse.data,
            risk: riskResponse.data,
            error: null
        });

    } catch (error) {
        console.error("Dashboard error:", error.message);

        res.render("dashboard", {
            analytics: null,
            risk: null,
            error: "Unable to load portfolio analytics."
        });
    }
})


const Document = require("./models/Document");

app.post("/upload", requireAuth, upload.single("file"), async (req, res) => {
    let documentRecord;

    try {
        if (
            !req.file ||
            path.extname(req.file.originalname).toLowerCase() !== ".pdf" ||
            req.file.mimetype !== "application/pdf"
        ) {
            return res.status(400).send("Please upload a valid PDF file.");
        }

        const clientId = req.session.user.clientId;

        const form = new FormData();
        form.append("client_id", clientId);

        form.append("file", req.file.buffer, {
            filename: req.file.originalname,
            contentType: "application/pdf"
        });

        documentRecord = await Document.create({
            clientId,
            originalName: req.file.originalname,
            storedName: req.file.originalname,
            fileSize: req.file.size,
            status: "processing"
        });
        
        const response = await axios.post(
            `${AI_URL}/upload`,
            form,
            {
                headers: {
                    ...form.getHeaders(),
                    "X-Service-Secret": process.env.AI_SERVICE_SECRET
                }
            }
        );

        
const extracted = response.data.portfolio;
console.log("EXTRACTED PORTFOLIO:");
console.log(JSON.stringify(extracted, null, 2));

console.log("TOTAL VALUE:", extracted?.total_value);
console.log("HOLDINGS:", extracted?.holdings);
if (
    !extracted ||
    !Array.isArray(extracted.holdings) ||
    extracted.holdings.length === 0 ||
    !Number.isFinite(extracted.total_value) ||
    extracted.total_value <= 0
) {
    throw new Error("Invalid portfolio data extracted from PDF.");
}

const holdings = extracted.holdings.map(item => ({
    name: item.name,
    assetClass: item.asset_class,
    value: item.value,
    page: item.page
}));

if (holdings.some(item =>
    !item.name ||
    !item.assetClass ||
    !Number.isFinite(item.value) ||
    item.value < 0 ||
    !Number.isInteger(item.page) ||
    item.page < 1
)) {
    throw new Error("Extracted holdings contain invalid data.");
}

const calculatedTotal = holdings.reduce(
    (sum, item) => sum + item.value,
    0
);

if (Math.abs(calculatedTotal - extracted.total_value) > 1) {
    throw new Error("Portfolio total does not match holding values.");
}

await Portfolio.findOneAndUpdate(
    { clientId },
    {
        clientId,
        currency: extracted.currency,
        totalValue: extracted.total_value,
        reportDate: extracted.report_date
            ? new Date(extracted.report_date)
            : new Date(),
        holdings
    },
    {
        upsert: true,
        new: true,
        runValidators: true
    }
);

await Document.findByIdAndUpdate(documentRecord._id, {
    totalChunks: response.data.total_chunks,
    status: "ready"
});

res.redirect("/");
    } catch (error) {
    console.error(
        "Upload error:",
        error.response?.data || error.message
    );

    if (documentRecord) {
        await Document.findByIdAndUpdate(documentRecord._id, {
            status: "failed"
        });
    }

    if (!res.headersSent) {
        res.status(500).send("Document upload failed.");
    }
}
});




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
        headers: {
            "X-Service-Secret": process.env.AI_SERVICE_SECRET
        }
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

app.post("/risk/explanation", requireAuth, async (req, res) => {
    try {
        const clientId = req.session.user.clientId;

        const portfolio = await Portfolio.findOne({
            clientId
        }).lean();

        if (!portfolio) {
            return res.status(404).json({
                error: "Portfolio not found."
            });
        }

        const portfolioPayload = {
            client_id: clientId,
            currency: portfolio.currency,
            holdings: portfolio.holdings.map(item => ({
                name: item.name,
                asset_class: item.assetClass,
                value: item.value,
                page: item.page
            }))
        };

        const response = await axios.post(
            `${AI_URL}/risk/explanation`,
            portfolioPayload,
            {
                headers: {
                    "X-Service-Secret": process.env.AI_SERVICE_SECRET
                }
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


app.post("/portfolio/sync", requireAuth, async (req, res) => {
    try {
        const filePath = path.join(__dirname, "../data/portfolio.json");

        const portfolioData = JSON.parse(
            fs.readFileSync(filePath, "utf8")
        );

        const clientId = req.session.user.clientId;

        const holdings = portfolioData.holdings.map(item => ({
            name: item.name,
            assetClass: item.asset_class,
            value: item.value,
            page: item.page
        }));

        const totalValue = holdings.reduce(
            (sum, item) => sum + item.value,
            0
        );

        const portfolio = await Portfolio.findOneAndUpdate(
            { clientId },
            {
                clientId,
                currency: portfolioData.currency,
                totalValue,
                reportDate: portfolioData.report_date,
                holdings
            },
            {
                new: true,
                upsert: true,
                runValidators: true
            }
        );

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

connectDB().then(() => {
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
        console.log(`WealthWise AI running at http://localhost:${PORT}`);
    });
}).catch(console.error);