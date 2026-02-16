const delay = ms => new Promise(res => setTimeout(res, ms));

        const removeElement = (xpath) => {
            try {
                let result = document.evaluate(xpath, document, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE, null);
                for (let i = result.snapshotLength - 1; i >= 0; i--) {
                    let node = result.snapshotItem(i);
                    if (node && node.parentNode) {
                        node.parentNode.removeChild(node);
                    }
                }
            } catch (err) {
                console.error("Error removing xpath: " + xpath, err);
            }
        };

        (async () => {
            // Wait slightly for dynamic content to settle
            await delay(100); 
            // --- INJECTED REMOVAL CALLS BELOW ---
            {REMOVAL_LOGIC}
            // ------------------------------------
        })();