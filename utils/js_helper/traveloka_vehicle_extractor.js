const paragraphXPath = {js_paragraph};
const buttonXPaths = {js_buttons}; // Array of XPaths
const containerXPath = {js_container};
const waitTime = {wait_ms};

// Helper: Get Element by XPath
const getElementByXPath = (xpath) => {
    try {
        return document.evaluate(
            xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;
    } catch (e) {
        return null;
    }
};

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const results = {};
const errors = [];
let buttonsFoundCount = 0;

try {
    // 1. Iterate through the provided list of XPaths
    if (Array.isArray(buttonXPaths)) {
        for (const btnXPath of buttonXPaths) {
            const button = getElementByXPath(btnXPath);

            // FALLBACK 1: If a specific button index doesn't exist, skip it silently.
            // This allows the Python config to define a range (e.g., 1-10) 
            // without failing on pages that only have 3 items.
            if (!button) {
                continue; 
            }

            buttonsFoundCount++;

            // Extract key (name) from the button before clicking
            let key = (button.innerText || button.textContent || "").trim();
            if (!key) key = "Item_" + buttonsFoundCount;

            // Click and Wait
            try {
                button.click();
                await sleep(waitTime);

                // Extract Content
                const pTag = getElementByXPath(paragraphXPath);
                
                // FALLBACK 2: If paragraph is missing, try to capture a generic error string
                // or simply log it as a specific content error, not a generic script crash.
                if (pTag) {
                    results[key] = (pTag.innerText || pTag.textContent).replace(/\s+/g, ' ').trim();
                } else {
                    // Try to see if the container itself has text if specific p-tag fails? 
                    // For now, we log this specific failure as it indicates broken content logic.
                    errors.push(`Content not found for: ${key}`);
                    results[key] = null; 
                }
            } catch (clickErr) {
                errors.push(`Interaction failed for: ${key} - ${clickErr.toString()}`);
            }
        }
    }

    // 2. Global Fallback Check
    // Only report a script-level error if WE FOUND NOTHING at all.
    if (buttonsFoundCount === 0) {
        errors.push("No buttons were found matching any of the provided XPaths.");
    }

    // 3. Cleanup Container (Optional)
    if (containerXPath) {
        const container = getElementByXPath(containerXPath);
        if (container) container.remove();
    }

    return { 
        success: true, 
        data: results, 
        meta: { 
            total_scanned: Array.isArray(buttonXPaths) ? buttonXPaths.length : 0,
            found: buttonsFoundCount 
        },
        errors: errors 
    };

} catch (err) {
    return { success: false, error: err.toString() };
}