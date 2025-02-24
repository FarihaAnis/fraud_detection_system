const puppeteer = require('puppeteer');

(async () => {
    // ✅ Launch Puppeteer
    const browser = await puppeteer.launch({ headless: true });

    // ✅ Open a new browser page
    const page = await browser.newPage();

    // ✅ Set viewport size
    await page.setViewport({ width: 1400, height: 1000 });

    // ✅ Navigate to your React app
    await page.goto('http://localhost:3000/', { waitUntil: 'networkidle2' });

    // ✅ Wait for charts to load (Use a different method for delays)
    await page.waitForSelector('.recharts-surface', { timeout: 10000 });

    // ✅ Use `evaluate()` to delay the execution inside the browser context
    await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 5000)));

    // ✅ Take a full-page screenshot
    await page.screenshot({ path: 'screenshot.png', fullPage: true });

    // ✅ Close the browser
    await browser.close();
    console.log("✅ Screenshot saved as 'screenshot.png'");
})();
