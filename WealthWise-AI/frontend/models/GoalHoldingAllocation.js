
const mongoose = require("mongoose");

const goalHoldingAllocationSchema = new mongoose.Schema({

    clientId: {
        type: String,
        required: true,
        index: true
    },

    goalId: {
        type: mongoose.Schema.Types.ObjectId,
        ref: "FinancialGoal",
        required: true
    },

    holdingKey: {
        type: String,
        required: true,
        trim: true
    },

    holdingName: {
        type: String,
        required: true,
        trim: true
    },

    amount: {
        type: Number,
        required: true,
        min: 0.01
    },

    currency: {
        type: String,
        default: "INR"
    }

}, {
    timestamps: true
});

// One allocation record per holding per goal
goalHoldingAllocationSchema.index(
    {
        clientId: 1,
        goalId: 1,
        holdingKey: 1
    },
    {
        unique: true
    }
);

// Efficient lookup of allocations across goals
goalHoldingAllocationSchema.index({
    clientId: 1,
    holdingKey: 1
});

module.exports = mongoose.model(
    "GoalHoldingAllocation",
    goalHoldingAllocationSchema
);
