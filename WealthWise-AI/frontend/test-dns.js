const dns2 = require("dns2");

const resolver = new dns2({
    dns: "8.8.8.8",
    port: 53,
    recursive: true
});

const hosts = [
    "ac-b2p7jzf-shard-00-00.svcst7l.mongodb.net",
    "ac-b2p7jzf-shard-00-01.svcst7l.mongodb.net",
    "ac-b2p7jzf-shard-00-02.svcst7l.mongodb.net"
];

async function testDNS() {
    for (const host of hosts) {
        const response = await resolver.resolve(host, "CNAME");

        console.log("\nHOST:", host);
        console.log("CANONICAL:", response.answers);
    }
}

testDNS().catch(console.error);