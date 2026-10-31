
const mongoose = require("mongoose");

const holdingSchema = new mongoose.Schema({
    name: {
        type: String,
        required: true
    },
    assetClass: {
        type: String,
        required: true
    },
    value: {
        type: Number,
        required: true,
        min: 0
    },
    page: {
        type: Number
    }
});

const portfolioSchema = new mongoose.Schema({
    clientId: {
        type: String,
        required: true,
        index: true
    },
    currency: {
        type: String,
        default: "INR"
    },
    totalValue: {
        type: Number,
        required: true,
        min: 0
    },
    reportDate: {
        type: Date,
        default: Date.now
    },
    holdings: [holdingSchema]
}, {
    timestamps: true
});

module.exports = mongoose.model("Portfolio", portfolioSchema);
