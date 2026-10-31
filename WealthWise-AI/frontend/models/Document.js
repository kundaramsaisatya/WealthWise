
const mongoose = require("mongoose");

const documentSchema = new mongoose.Schema({
    clientId: {
        type: String,
        required: true,
        index: true
    },
    originalName: {
        type: String,
        required: true
    },
    storedName: {
        type: String,
        required: true
    },
    fileType: {
        type: String,
        default: "application/pdf"
    },
    fileSize: {
        type: Number
    },
    totalChunks: {
        type: Number,
        default: 0
    },
    status: {
        type: String,
        enum: ["processing", "ready", "failed"],
        default: "processing"
    }
}, {
    timestamps: true
});

module.exports = mongoose.model("Document", documentSchema);
