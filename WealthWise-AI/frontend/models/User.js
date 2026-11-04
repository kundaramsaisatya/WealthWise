
const mongoose = require("mongoose");

const userSchema = new mongoose.Schema({
    name: {
        type: String,
        required: true,
        trim: true
    },
    email: {
        type: String,
        required: true,
        unique: true,
        lowercase: true,
        trim: true
    },
    password: {
        type: String,
        required: true
    },
    riskTolerance: {
    type: String,
    enum: ["conservative", "moderate", "aggressive"],
    default: null
    },
    clientId: {
        type: String,
        unique: true,
        required: true
    }
}, {
    timestamps: true
});

module.exports = mongoose.model("User", userSchema);
