const btch = require('btch-downloader');
const url = process.argv[2];

if (!url) {
    console.log(JSON.stringify({ status: false, message: "URL kosong" }));
    process.exit(1);
}

async function scrape() {
    try {
        const result = await btch.threads(url);
        console.log(JSON.stringify(result));
    } catch (error) {
        console.log(JSON.stringify({ status: false, message: error.message }));
    }
}

scrape();