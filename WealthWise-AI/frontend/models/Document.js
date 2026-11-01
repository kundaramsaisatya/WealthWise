
const mongoose = require("mongoose");

const documentSchema = new mongoose.Schema({
    clientId: {
        type: String,
        required: true,
        index: true
    },

    originalName: {
        type: String,
        required: true,
        trim: true
    },

    storedName: {
        type: String,
        required: true
    },

    fileType: {
        type: String,
        enum: ["pdf", "xlsx"],
        required: true
    },

    fileSize: {
        type: Number,
        default: 0
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

documentSchema.index({ clientId: 1, createdAt: -1 });

module.exports = mongoose.model("Document", documentSchema);
