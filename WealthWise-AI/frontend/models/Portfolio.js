
const mongoose = require("mongoose");

// --------------------------------------------------
// HOLDING SCHEMA
// --------------------------------------------------

const holdingSchema = new mongoose.Schema({

    name: {
        type: String,
        required: true,
        trim: true
    },

    assetClass: {
        type: String,
        default: "Other",
        trim: true
    },

    subCategory: {
        type: String,
        default: null
    },

    isin: {
        type: String,
        default: null,
        trim: true
    },

    quantity: {
        type: Number,
        default: null
    },

    investedValue: {
        type: Number,
        default: null,
        min: 0
    },

    currentValue: {
        type: Number,
        default: null,
        min: 0
    },

    profitLoss: {
        type: Number,
        default: null
    },

    profitLossPercentage: {
        type: Number,
        default: null
    },

    folioNumber: {
        type: String,
        default: null,
        trim: true
    },

    // Explicit folio-level KYC and nominee metadata from statement schedules.
    folioVerification: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },

    source: {
        type: String,
        default: null
    },

    averageNav: {
        type: Number,
        default: null
    },

    currentNav: {
        type: Number,
        default: null
    },

    page: {
        type: Number,
        default: null,
        min: 1
    },

    rowNumber: {
        type: Number,
        default: null,
        min: 1
    }

});


// --------------------------------------------------
// PORTFOLIO SCHEMA
// --------------------------------------------------

const portfolioSchema = new mongoose.Schema({

    clientId: {
        type: String,
        required: true,
        index: true
    },

    documentId: {
        type: mongoose.Schema.Types.ObjectId,
        ref: "Document",
        default: null
    },

    documentName: {
        type: String,
        default: null
    },

    documentType: {
        type: String,
        enum: ["pdf", "xlsx"],
        default: null
    },

    isDemo: {
        type: Boolean,
        default: false
    },

    currency: {
        type: String,
        default: "INR"
    },

    // Explicit account-holder identity extracted from statement metadata.
    // Used to prevent unrelated people's statements being consolidated.
    accountHolder: {
        type: String,
        default: null,
        trim: true,
        maxlength: 120
    },

    totalValue: {
        type: Number,
        required: true,
        min: 0,
        default: 0
    },

    // Provenance of the portfolio-level valuation used for history.
    totalValueSource: {
        type: String,
        enum: ["reported", "holdings", "incomplete"],
        default: "incomplete"
    },

    // Actual statement/report date.
    // Never automatically substitute upload date.

    reportDate: {
        type: Date,
        default: null
    },

    holdings: {
        type: [holdingSchema],
        default: []
    }

}, {
    timestamps: true
});


// --------------------------------------------------
// INDEXES
// --------------------------------------------------

portfolioSchema.index({
    clientId: 1,
    reportDate: -1
});

portfolioSchema.index({
    clientId: 1,
    documentId: 1
});


// --------------------------------------------------
// MODEL
// --------------------------------------------------

module.exports = mongoose.model(
    "Portfolio",
    portfolioSchema
);
