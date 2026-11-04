
const mongoose = require("mongoose");

const financialGoalSchema = new mongoose.Schema({

    clientId: {
        type: String,
        required: true,
        index: true
    },

    name: {
        type: String,
        required: true,
        trim: true,
        maxlength: 100
    },

    category: {
        type: String,
        required: true,
        enum: [
            "Retirement",
            "House",
            "Education",
            "Travel",
            "Emergency Fund",
            "Other"
        ]
    },

    targetAmount: {
        type: Number,
        required: true,
        min: 1
    },

    currentSavings: {
        type: Number,
        default: 0,
        min: 0
    },
    portfolioAllocatedAmount: {
        type: Number,
        default: 0,
        min: 0
    },

    targetDate: {
        type: Date,
        required: true
    },

    inflationRate: {
        type: Number,
        default: 6,
        min: 0,
        max: 30
    },

    expectedAnnualReturn: {
        type: Number,
        default: 10,
        min: 0,
        max: 50
    },

    monthlyContribution: {
        type: Number,
        default: 0,
        min: 0
    },

    status: {
        type: String,
        enum: ["Active", "Completed", "Paused"],
        default: "Active"
    }

}, {
    timestamps: true
});

financialGoalSchema.index({
    clientId: 1,
    status: 1,
    targetDate: 1
});

module.exports = mongoose.model(
    "FinancialGoal",
    financialGoalSchema
);
