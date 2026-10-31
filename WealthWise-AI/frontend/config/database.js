const mongoose = require("mongoose");
const dns2 = require("dns2");

const resolver = new dns2({
    dns: "8.8.8.8",
    port: 53,
    recursive: true
});

async function connectDB() {
    try {
        const uri = new URL(process.env.MONGODB_URI);
        const srvDomain = uri.hostname; // e.g., cluster0.xxxx.mongodb.net

        // Resolve MongoDB Atlas SRV records
        const response = await resolver.resolve(
            `_mongodb._tcp.${srvDomain}`,
            "SRV"
        );

        const records = response.answers.filter(
            record => record.type === 33
        );

        if (records.length === 0) {
            throw new Error("No MongoDB Atlas shard records found.");
        }

        const hosts = records.map(record => `${record.target}:${record.port}`);

        console.log("MongoDB hosts discovered:", hosts);

        // Build a standard MongoDB connection string
        const username = encodeURIComponent(
            decodeURIComponent(uri.username)
        );

        const password = encodeURIComponent(
            decodeURIComponent(uri.password)
        );

        const database = uri.pathname || "/";
        const searchParams = uri.search; // Preserves query params like ?retryWrites=true&w=majority

        const connectionString =
            `mongodb://${username}:${password}@${hosts.join(",")}${database}${searchParams}`;

        mongoose.set("debug", true);
        await mongoose.connect(connectionString, {
            tls: true,
            authSource: "admin",
            serverSelectionTimeoutMS: 15000,
            connectTimeoutMS: 10000,
            heartbeatFrequencyMS: 5000
        });

        console.log("MongoDB connected successfully!");

        return mongoose.connection.getClient();

    } catch (error) {
        console.error("MongoDB connection failed:");
        console.dir(error, { depth: 6 });
        throw error;
    }
}

module.exports = connectDB;