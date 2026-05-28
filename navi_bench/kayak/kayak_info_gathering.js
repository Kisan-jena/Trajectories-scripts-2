(() => {
    const results = [];
    const url = window.location.href;

    const getText = (el) => {
        if (!el) return null;
        let text = el.innerText || el.textContent || '';
        return text.replace(/\u00A0/g, ' ').trim().replace(/\s+/g, ' ');
    };

    const Parsers = {
        price: (text) => {
            if (!text) return null;
            // Captures currency symbol (Group 1) and amount (Group 2)
            let match = text.match(/([$€£₹]|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)/i);
            if (match && match[2]) {
                // Parse float and return exactly as is (No conversion)
                return parseFloat(match[2].replace(/,/g, ""));
            }
            return null;
        },

        stops: (text) => {
            if (!text) return null;
            if (/direct|nonstop|non-stop/i.test(text)) return 0;
            let match = text.match(/(\d+)\s*stop/i);
            if (match) return parseInt(match[1]);
            return null;
        }
    };

    const Scraper = {
        urlMetadata: () => {
            let meta = {};
            if (url.includes('/flights/')) {
                const match = url.match(/\/flights\/([A-Za-z]{3})-([A-Za-z]{3})\/(\d{4}-\d{2}-\d{2})/i);
                if (match) meta = { origin: match[1], destination: match[2], departDate: match[3] };
            } else if (url.includes('/cars/')) {
                // Fix: URL format is /cars/LOCATION/PICKUP_DATE/DROPOFF_DATE
                const match = url.match(/\/cars\/([^\/]+)\/(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})/i);
                if (match) meta = { pickUpLocation: match[1], pickUpDate: match[2], dropOffDate: match[3] };
            } else if (url.includes('/hotels/')) {
                const match = url.match(/\/hotels\/([^\/]+)\/(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})/i);
                if (match) meta = { city: match[1], checkIn: match[2], checkOut: match[3] };
            }
            return meta;
        },

        filters: () => {
            const f = { filterAirlines: [], filterStops: [], filterMaxPrice: null };
            if (!url.includes('/flights/')) return f;

            try {
                const airNodes = document.querySelectorAll('div[role="region"][aria-label="Airlines"] input[type="checkbox"]:checked:not([disabled])');
                airNodes.forEach(n => {
                    const lbl = n.closest('.hYzH-filter-checkbox-outer')?.querySelector('.hYzH-checkbox-label');
                    if (lbl) f.filterAirlines.push(getText(lbl));
                });

                const stopNodes = document.querySelectorAll('div[role="region"][aria-label="Stops"] input[type="checkbox"]:checked:not([disabled])');
                stopNodes.forEach(n => {
                    const lbl = n.closest('.hYzH-filter-checkbox-outer')?.querySelector('.hYzH-checkbox-label');
                    if (lbl) f.filterStops.push(getText(lbl));
                });

                // Max Price Slider (Removed conversion logic)
                const priceNode = document.querySelector('div[role="region"][aria-label="Price"] span[role="slider"]');
                if (priceNode && priceNode.getAttribute('aria-valuenow')) {
                    f.filterMaxPrice = parseFloat(priceNode.getAttribute('aria-valuenow'));
                }
            } catch (e) { console.error("Filter parse error", e); }
            return f;
        },

        flightListings: () => {
            const collected = [];
            // Target the specific wrapper seen in your HTML
            const rows = document.querySelectorAll('.nrc6-wrapper');

            rows.forEach(row => {
                try {
                    const rowText = getText(row);

                    // 1. Extract Price (Prioritize the dedicated price class)
                    const priceNode = row.querySelector('.e2GB-price-text') || row.querySelector('[class*="price-text"]');
                    const extractedPrice = Parsers.price(getText(priceNode) || rowText);

                    // 2. Extract Airline (Target the alt text or the specific text div)
                    const airlineImg = row.querySelector('.c5iUd-leg-carrier img');
                    const airlineDiv = row.querySelector('.c_cgF[dir="ltr"]');
                    const airlineText = airlineImg?.alt || getText(airlineDiv) || "Unknown";

                    // 3. Extract Times (Target the time container)
                    let departTime = "XX:XX", arrivalTime = "XX:XX";
                    const timeDiv = row.querySelector('.vmXl-mod-variant-large');
                    if (timeDiv) {
                        const rawTime = getText(timeDiv);
                        // This regex handles standard hyphens, En-dashes, and Em-dashes
                        const timeMatch = rawTime.match(/(\d{1,2}:\d{2}\s*(?:am|pm)?)\s*[\-–—]\s*(\d{1,2}:\d{2}\s*(?:am|pm)?)/i);
                        if (timeMatch) {
                            departTime = timeMatch[1];
                            arrivalTime = timeMatch[2];
                        }
                    }

                    // 4. Extract Cabin Class (NEW)
                    let cabinClass = null;

                    // Try common UI locations first
                    const cabinNode =
                        row.querySelector('[class*="cabin"]') ||
                        row.querySelector('[aria-label*="cabin"]') ||
                        row.querySelector('[data-testid*="cabin"]') ||
                        row.querySelector('[class*="class"]');

                    // fallback: scan row text
                    if (cabinNode) {
                        cabinClass = getText(cabinNode);
                    } else {
                        const m = rowText.match(/(premium economy|business class|first class|economy|business|first)/i);
                        if (m) cabinClass = m[1];
                    }

                    const stops = Parsers.stops(rowText);

                    const formattedStops = stops === 0 ? "Direct" : (stops === null ? null : `${stops} Stops`);

                    if (extractedPrice) {
                        collected.push({
                            source: "dom_flight_listing",
                            airline: airlineText,
                            price: extractedPrice,
                            stops: formattedStops,
                            departTime,
                            arrivalTime,
                            cabinClass:
                                (
                                    cabinClass || ""
                                ).toLowerCase()
                        });
                    }
                } catch (e) { console.error("Flight row error", e); }
            });
            return collected;
        },

        carListings: () => {
            // Unchanged
            const collected = [];
            const cards = document.querySelectorAll('.jo6g-car-result-item');
            cards.forEach(card => {
                try {
                    const titleNode = card.querySelector('.js-title');
                    const categoryNode = card.querySelector('.MseY-sub-title');
                    const priceNode = card.querySelector('.c4nz8-price-total') || card.querySelector('[class*="price-total"]');
                    const extractedPrice = Parsers.price(getText(priceNode));
                    const providerNode = card.querySelector('.EuxN-provider-name');
                    const agencyImg = card.querySelector('img[alt^="Car agency:"]');
                    const agencyName = agencyImg ? agencyImg.getAttribute('alt').replace('Car agency:', '').trim() : '';
                    let passengers = null, bags = null, doors = null, transmission = null;
                    const featureNodes = card.querySelectorAll('[role="listitem"]');
                    featureNodes.forEach(f => {
                        const aria = f.getAttribute('aria-label') || '';
                        const text = getText(f);
                        if (aria.includes('Passengers')) passengers = parseInt(text);
                        if (aria.includes('Bags')) bags = parseInt(text);
                        if (aria.includes('doors')) doors = parseInt(text);
                        if (aria.includes('Transmission')) transmission = text;
                    });
                    if (extractedPrice) {
                        collected.push({
                            source: "dom_car_listing",
                            title: getText(titleNode),
                            category: getText(categoryNode),
                            price: extractedPrice,
                            provider: getText(providerNode),
                            agency: agencyName,
                            passengers, bags, doors, transmission
                        });
                    }
                } catch (e) { }
            });
            return collected;
        },

        hotelListings: () => {
            // Unchanged
            const collected = [];
            const cards = document.querySelectorAll('.yuAt[role="group"]');
            cards.forEach(card => {
                try {
                    const nameNode = card.querySelector('.c9Hnq-big-name');
                    const name = getText(nameNode);
                    if (!name) return;
                    const priceNode = card.querySelector('[data-target="price"]') || card.querySelector('.c1XBO') || card.querySelector('.Ptt7-price');
                    const extractedPrice = Parsers.price(getText(priceNode));
                    const scoreNode = card.querySelector('.c9kNN');
                    const score = scoreNode && getText(scoreNode) !== "-" ? parseFloat(getText(scoreNode)) : null;
                    const starNode = card.querySelector('.hEI8');
                    const starsText = getText(starNode);
                    const starsMatch = starsText ? starsText.match(/(\d+)\s*stars?/i) : null;
                    const stars = starsMatch ? parseInt(starsMatch[1]) : 0;
                    const providerImg = card.querySelector('img[class*="provider-logo"]');
                    const provider = providerImg ? providerImg.getAttribute('alt') : '';
                    const freebies = [];
                    const freebieNodes = card.querySelectorAll('.BNDX, .iyw8-freebies');
                    freebieNodes.forEach(n => {
                        const txt = getText(n) || n.getAttribute('title');
                        if (txt) {
                            txt.split(',').forEach(f => {
                                const clean = f.trim();
                                if (clean && !freebies.includes(clean)) freebies.push(clean);
                            });
                        }
                    });
                    const locNode = card.querySelector('.upS4-big-name');
                    const location = getText(locNode);

                    if (extractedPrice) {
                        collected.push({
                            source: "dom_hotel_listing",
                            title: name,
                            price: extractedPrice,
                            score: score,
                            stars: stars,
                            provider: provider,
                            freebies: freebies,
                            location: location
                        });
                    }
                } catch (e) { }
            });
            return collected;
        }
    };

    try {
        let scraped = [];
        let pageType = 'other';
        if (url.includes('/flights/')) {
            pageType = 'flight_results';
            scraped.push(...Scraper.flightListings());
        } else if (url.includes('/cars/')) {
            pageType = 'car_results';
            scraped.push(...Scraper.carListings());
        } else if (url.includes('/hotels/')) {
            pageType = 'hotel_results';
            scraped.push(...Scraper.hotelListings());
        }

        const antiBotStatus = document.body.innerText.toLowerCase().includes('challenge-running') ? 'blocked_cloudflare' : 'clear';
        const activeFilters = Scraper.filters();
        const urlData = Scraper.urlMetadata();

        scraped.forEach(item => {
            results.push({ ...item, ...activeFilters, ...urlData, pageType, antiBotStatus });
        });
    } catch (e) { console.error("Kayak Scraper failed", e); }

    return results;
})();































// (() => {
//     const results = [];
//     const url = window.location.href;

//     const getText = (el) => {
//         if (!el) return null;
//         let text = el.innerText || el.textContent || '';
//         return text.replace(/\u00A0/g, ' ').trim().replace(/\s+/g, ' ');
//     };

//     // querySelector with multiple fallback selectors — returns first match or null
//     const queryFirst = (root, ...selectors) => {
//         for (const sel of selectors) {
//             try {
//                 const el = root.querySelector(sel);
//                 if (el) return el;
//             } catch (e) {}
//         }
//         return null;
//     };

//     const Parsers = {
//         price: (text) => {
//             if (!text) return null;
//             let match = text.match(/([$€£₹]|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)/i);
//             if (match && match[2]) {
//                 let amount = parseFloat(match[2].replace(/,/g, ""));
//                 let symbol = (match[1] || "").toLowerCase();
//                 if (symbol === '$') amount *= 83.0;
//                 else if (symbol === '€') amount *= 90.0;
//                 else if (symbol === '£') amount *= 105.0;
//                 return amount;
//             }
//             return null;
//         },

//         stops: (text) => {
//             if (!text) return null;
//             if (/direct|nonstop|non-stop/i.test(text)) return 0;
//             let match = text.match(/(\d+)\s*stop/i);
//             if (match) return parseInt(match[1]);
//             return null;
//         },

//         // Extract price from a container by scanning all descendant text nodes for ₹/$/€ patterns
//         priceFromContainer: (container) => {
//             if (!container) return null;
//             // 1. Try common semantic candidates first (price is often in a bolded or large span)
//             const candidates = container.querySelectorAll(
//                 '[class*="price"], [class*="fare"], [class*="amount"], [class*="cost"], ' +
//                 '[data-testid*="price"], [aria-label*="price"], [aria-label*="fare"]'
//             );
//             for (const el of candidates) {
//                 const p = Parsers.price(getText(el));
//                 if (p !== null) return p;
//             }
//             // 2. Fall back to scanning all text in the container for a currency pattern
//             const fullText = getText(container);
//             return Parsers.price(fullText);
//         }
//     };

//     const Scraper = {
//         urlMetadata: () => {
//             let meta = {};
//             if (url.includes('/flights/')) {
//                 const match = url.match(/\/flights\/([A-Za-z]{3})-([A-Za-z]{3})\/(\d{4}-\d{2}-\d{2})/i);
//                 if (match) meta = { origin: match[1], destination: match[2], departDate: match[3] };
//             } else if (url.includes('/cars/')) {
//                 const match = url.match(/\/cars\/([^\/]+)\/([^\/]+)\/(\d{4}-\d{2}-\d{2})/i);
//                 if (match) meta = { pickUpLocation: match[1], dropOffLocation: match[2], pickUpDate: match[3] };
//             } else if (url.includes('/hotels/')) {
//                 const match = url.match(/\/hotels\/([^\/]+)\/(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})/i);
//                 if (match) meta = { city: match[1], checkIn: match[2], checkOut: match[3] };
//             }
//             return meta;
//         },

//         filters: () => {
//             const f = { filterAirlines: [], filterStops: [], filterMaxPrice: null };
//             if (!url.includes('/flights/')) return f;

//             try {
//                 // ── Airline checkboxes ────────────────────────────────────────────────────
//                 // ARIA-stable: the "Airlines" region label never changes
//                 const airRegion = document.querySelector(
//                     'div[role="region"][aria-label="Airlines"], ' +
//                     'div[role="region"][aria-label*="irline"], ' +
//                     'section[aria-label*="irline"]'
//                 );
//                 if (airRegion) {
//                     airRegion.querySelectorAll('input[type="checkbox"]:checked:not([disabled])').forEach(n => {
//                         // Walk up to the checkbox row, then grab the label text
//                         const row = n.closest('label') || n.closest('li') || n.parentElement;
//                         if (row) {
//                             // Exclude the checkbox's own aria-label if it duplicates; prefer visible text
//                             const lbl = queryFirst(row,
//                                 '[class*="label"]', '[class*="name"]', '[class*="text"]', 'span', 'div'
//                             );
//                             const txt = lbl ? getText(lbl) : getText(row);
//                             if (txt && !f.filterAirlines.includes(txt)) f.filterAirlines.push(txt);
//                         }
//                     });
//                 }

//                 // ── Stop checkboxes ───────────────────────────────────────────────────────
//                 const stopRegion = document.querySelector(
//                     'div[role="region"][aria-label="Stops"], ' +
//                     'div[role="region"][aria-label*="top"], ' +
//                     'section[aria-label*="top"]'
//                 );
//                 if (stopRegion) {
//                     stopRegion.querySelectorAll('input[type="checkbox"]:checked:not([disabled])').forEach(n => {
//                         const row = n.closest('label') || n.closest('li') || n.parentElement;
//                         if (row) {
//                             const lbl = queryFirst(row, '[class*="label"]', '[class*="text"]', 'span', 'div');
//                             const txt = lbl ? getText(lbl) : getText(row);
//                             if (txt && !f.filterStops.includes(txt)) f.filterStops.push(txt);
//                         }
//                     });
//                 }

//                 // ── Price slider ──────────────────────────────────────────────────────────
//                 const priceSlider = document.querySelector(
//                     'div[role="region"][aria-label="Price"] span[role="slider"], ' +
//                     'div[role="region"][aria-label*="rice"] span[role="slider"], ' +
//                     'input[type="range"][aria-label*="rice"], ' +
//                     'span[role="slider"][aria-label*="rice"]'
//                 );
//                 if (priceSlider) {
//                     let val = parseFloat(priceSlider.getAttribute('aria-valuenow'));
//                     const valueText = priceSlider.getAttribute('aria-valuetext') || '';
//                     if (valueText.includes('$')) val *= 83.0;
//                     else if (valueText.includes('€')) val *= 90.0;
//                     else if (valueText.includes('£')) val *= 105.0;
//                     f.filterMaxPrice = isNaN(val) ? null : val;
//                 }
//             } catch (e) { console.error("Filter parse error", e); }
//             return f;
//         },

//         flightListings: () => {
//             const collected = [];
//             // ARIA-stable container — Kayak has used this consistently
//             const rows = document.querySelectorAll(
//                 'div[role="group"][aria-label^="Result item"], ' +
//                 'div[role="listitem"][aria-label^="Result"], ' +
//                 'li[role="listitem"][aria-label^="Result"]'
//             );

//             rows.forEach(row => {
//                 try {
//                     const rowText = getText(row);
//                     if (!rowText) return;

//                     // ── Price ─────────────────────────────────────────────────────────────
//                     // Try multiple selector patterns; fall back to scanning the full row text
//                     const priceEl = queryFirst(row,
//                         '[class*="price-text"]',
//                         '[class*="price_text"]',
//                         '[class*="farePrice"]',
//                         '[class*="fare-price"]',
//                         '[class*="price"]',
//                         '[data-testid*="price"]',
//                         '[aria-label*="price"]',
//                         '[aria-label*="fare"]'
//                     );
//                     const extractedPrice = Parsers.price(priceEl ? getText(priceEl) : rowText);

//                     // ── Airline ───────────────────────────────────────────────────────────
//                     const airlineEl = queryFirst(row,
//                         '[class*="operator-text"]',
//                         '[class*="operator_text"]',
//                         '[class*="carrier-text"]',
//                         '[class*="carrier_text"]',
//                         '[class*="airlineName"]',
//                         '[class*="airline-name"]',
//                         '[class*="airline_name"]',
//                         '[class*="companyName"]',
//                         '[data-testid*="airline"]',
//                         '[data-testid*="carrier"]'
//                     );
//                     const airlineText = airlineEl ? getText(airlineEl) : '';

//                     // ── Stops ─────────────────────────────────────────────────────────────
//                     const extractedStops = Parsers.stops(rowText);

//                     // ── Departure / Arrival times ─────────────────────────────────────────
//                     let departTime = null, arrivalTime = null;

//                     // Strategy 1: look for a "large variant" time display
//                     const timeEl = queryFirst(row,
//                         '[class*="variant-large"]',
//                         '[class*="variant_large"]',
//                         '[class*="time-large"]',
//                         '[class*="depart-time"]',
//                         '[class*="departTime"]',
//                         '[class*="times"]',
//                         '[data-testid*="time"]'
//                     );
//                     if (timeEl) {
//                         const tm = getText(timeEl).match(/(\d{1,2}:\d{2})\s*[–\-–]\s*(\d{1,2}:\d{2})/);
//                         if (tm) { departTime = tm[1]; arrivalTime = tm[2]; }
//                     }

//                     // Strategy 2: parse aria-label on the row's checkbox (very stable)
//                     if (!departTime) {
//                         const cb = row.querySelector('input[type="checkbox"]');
//                         if (cb) {
//                             const label = cb.getAttribute('aria-label') || '';
//                             const tm = label.match(/([A-Z]{3})\s+(\d{1,2}:\d{2})\s*-\s*([A-Z]{3})\s+(\d{1,2}:\d{2})/);
//                             if (tm) { departTime = tm[2]; arrivalTime = tm[4]; }
//                         }
//                     }

//                     // Strategy 3: scan raw text for HH:MM – HH:MM
//                     if (!departTime) {
//                         const tm = rowText.match(/(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})/);
//                         if (tm) { departTime = tm[1]; arrivalTime = tm[2]; }
//                     }

//                     // ── Cabin ─────────────────────────────────────────────────────────────
//                     let cabinText = '';
//                     const cabinEl = queryFirst(row,
//                         '[aria-label*="Cabin"]',
//                         '[class*="cabin"]',
//                         '[data-testid*="cabin"]'
//                     );
//                     if (cabinEl) {
//                         cabinText = getText(cabinEl);
//                     } else {
//                         const m = rowText.match(/(premium economy|first class|business class|economy)/i);
//                         if (m) cabinText = m[1];
//                     }

//                     if (extractedPrice) {
//                         collected.push({
//                             source: "dom_flight_listing",
//                             airline: airlineText.toLowerCase(),
//                             price: extractedPrice,
//                             stops: extractedStops,
//                             departTime,
//                             arrivalTime,
//                             cabinClass: cabinText
//                         });
//                     }
//                 } catch (e) {}
//             });
//             return collected;
//         },

//         carListings: () => {
//             const collected = [];
//             // Old selector: .jo6g-car-result-item  → replaced with stable fallback chain
//             const cards = document.querySelectorAll(
//                 '[class*="car-result-item"], ' +
//                 '[class*="carResultItem"], ' +
//                 '[class*="carResult"], ' +
//                 '[data-testid*="car-result"], ' +
//                 '[data-testid*="carResult"], ' +
//                 'li[class*="result"], ' +
//                 'div[class*="result"][data-resultid]'
//             );

//             cards.forEach(card => {
//                 try {
//                     // ── Title ─────────────────────────────────────────────────────────────
//                     const titleEl = queryFirst(card,
//                         '[class*="title"]', '[class*="carName"]', '[class*="car-name"]',
//                         'h2', 'h3', '[data-testid*="title"]', '[aria-label*="car"]'
//                     );
//                     // ── Category ──────────────────────────────────────────────────────────
//                     const categoryEl = queryFirst(card,
//                         '[class*="sub-title"]', '[class*="subtitle"]', '[class*="category"]',
//                         '[class*="carType"]', '[class*="car-type"]', '[data-testid*="category"]'
//                     );
//                     // ── Price ─────────────────────────────────────────────────────────────
//                     const priceEl = queryFirst(card,
//                         '[class*="price-total"]', '[class*="priceTotal"]',
//                         '[class*="totalPrice"]', '[class*="total-price"]',
//                         '[class*="price"]', '[data-testid*="price"]', '[aria-label*="price"]'
//                     );
//                     const extractedPrice = Parsers.price(priceEl ? getText(priceEl) : getText(card));

//                     // ── Provider ──────────────────────────────────────────────────────────
//                     const providerEl = queryFirst(card,
//                         '[class*="provider-name"]', '[class*="providerName"]',
//                         '[class*="supplier"]', '[data-testid*="provider"]'
//                     );
//                     const agencyImg = card.querySelector('img[alt^="Car agency:"], img[alt*="agency"]');
//                     const agencyName = agencyImg
//                         ? agencyImg.getAttribute('alt').replace(/car agency:/i, '').trim()
//                         : '';

//                     // ── Features (passengers, bags, doors, transmission) ──────────────────
//                     let passengers = null, bags = null, doors = null, transmission = null;
//                     card.querySelectorAll('[role="listitem"]').forEach(f => {
//                         const aria = f.getAttribute('aria-label') || '';
//                         const text = getText(f);
//                         if (/passenger/i.test(aria)) passengers = parseInt(text);
//                         if (/bag/i.test(aria)) bags = parseInt(text);
//                         if (/door/i.test(aria)) doors = parseInt(text);
//                         if (/transmission/i.test(aria)) transmission = text;
//                     });

//                     // Fallback: parse raw card text for passenger count
//                     if (passengers === null) {
//                         const m = getText(card).match(/(\d+)\s*passenger/i);
//                         if (m) passengers = parseInt(m[1]);
//                     }

//                     if (extractedPrice) {
//                         collected.push({
//                             source: "dom_car_listing",
//                             title: getText(titleEl),
//                             category: getText(categoryEl),
//                             price: extractedPrice,
//                             provider: getText(providerEl),
//                             agency: agencyName,
//                             passengers,
//                             bags,
//                             doors,
//                             transmission
//                         });
//                     }
//                 } catch (e) { console.error('Car card parse error', e); }
//             });
//             return collected;
//         },

//         hotelListings: () => {
//             const collected = [];
//             // Old selector: .yuAt[role="group"]
//             // The role="group" is stable; the class prefix is not. Try multiple fallbacks.
//             const cards = document.querySelectorAll(
//                 '[class*="yuAt"][role="group"], ' +       // keep old name as first try
//                 'div[role="group"][data-resultid], ' +
//                 'li[role="group"], ' +
//                 'article[role="group"], ' +
//                 'div[class*="hotelResult"][role="group"], ' +
//                 'div[class*="hotel-result"][role="group"], ' +
//                 'div[class*="PropertyCard"], ' +
//                 'div[class*="property-card"]'
//             );

//             cards.forEach(card => {
//                 try {
//                     // ── Hotel Name ────────────────────────────────────────────────────────
//                     const nameEl = queryFirst(card,
//                         '[class*="big-name"]', '[class*="bigName"]',
//                         '[class*="hotelName"]', '[class*="hotel-name"]',
//                         '[class*="propertyName"]', '[class*="property-name"]',
//                         '[data-testid*="name"]', '[aria-label*="hotel"]',
//                         'h2', 'h3'
//                     );
//                     const name = getText(nameEl);
//                     if (!name) return;

//                     // ── Price ─────────────────────────────────────────────────────────────
//                     const priceEl = queryFirst(card,
//                         '[data-target="price"]',
//                         '[class*="price-total"]', '[class*="priceTotal"]',
//                         '[class*="c1XBO"]',       // keep old class as a try
//                         '[class*="Ptt7"]',        // keep old class as a try
//                         '[class*="price"]',
//                         '[data-testid*="price"]',
//                         '[aria-label*="price"]'
//                     );
//                     const extractedPrice = Parsers.price(priceEl ? getText(priceEl) : null)
//                         || Parsers.priceFromContainer(card);

//                     // ── Review Score ──────────────────────────────────────────────────────
//                     // Kayak scores are decimals like 8.5, 9.1 — look for those patterns
//                     const scoreEl = queryFirst(card,
//                         '[class*="c9kNN"]',           // keep old class as a try
//                         '[class*="score"]', '[class*="rating"]',
//                         '[class*="reviewScore"]', '[class*="review-score"]',
//                         '[class*="guestRating"]',
//                         '[data-testid*="score"]', '[data-testid*="rating"]',
//                         '[aria-label*="score"]', '[aria-label*="rating"]'
//                     );
//                     let score = null;
//                     if (scoreEl) {
//                         const scoreText = getText(scoreEl);
//                         if (scoreText && scoreText !== '-') {
//                             const parsed = parseFloat(scoreText);
//                             if (!isNaN(parsed) && parsed > 0 && parsed <= 10) score = parsed;
//                         }
//                     }
//                     // Fallback: scan all text nodes in the card for a standalone decimal
//                     if (score === null) {
//                         const cardText = getText(card);
//                         const sm = cardText.match(/\b([89]\.\d|10\.0|[5-9]\.\d)\b/);
//                         if (sm) score = parseFloat(sm[1]);
//                     }

//                     // ── Star Rating ───────────────────────────────────────────────────────
//                     const starEl = queryFirst(card,
//                         '[class*="hEI8"]',            // keep old class as a try
//                         '[class*="stars"]', '[class*="starRating"]', '[class*="star-rating"]',
//                         '[aria-label*="star"]',
//                         '[data-testid*="star"]'
//                     );
//                     let stars = 0;
//                     if (starEl) {
//                         const starLabel = starEl.getAttribute('aria-label') || getText(starEl) || '';
//                         const sm = starLabel.match(/(\d+)\s*star/i);
//                         if (sm) stars = parseInt(sm[1]);
//                         // Fallback: count star SVG/icon children
//                         if (!stars) {
//                             const icons = starEl.querySelectorAll('svg, [class*="star-icon"], [class*="starIcon"]');
//                             if (icons.length > 0) stars = icons.length;
//                         }
//                     }
//                     // Fallback: parse text of the entire card
//                     if (!stars) {
//                         const cardText = getText(card);
//                         const sm = cardText.match(/(\d)\s*-?\s*star/i);
//                         if (sm) stars = parseInt(sm[1]);
//                     }

//                     // ── Provider / OTA ────────────────────────────────────────────────────
//                     const providerImg = queryFirst(card,
//                         'img[class*="provider-logo"]',
//                         'img[class*="providerLogo"]',
//                         'img[alt*="provider"]',
//                         'img[alt*="booking"]',
//                         'img[alt*="hotels"]'
//                     );
//                     const provider = providerImg ? providerImg.getAttribute('alt') : '';

//                     // ── Freebies / Amenities ──────────────────────────────────────────────
//                     const freebies = [];
//                     const freebieEls = card.querySelectorAll(
//                         '[class*="BNDX"], [class*="freebies"], [class*="freebie"], ' +
//                         '[class*="amenities"], [class*="amenity"], ' +
//                         '[class*="perk"], [data-testid*="freebie"], [data-testid*="amenity"]'
//                     );
//                     freebieEls.forEach(n => {
//                         const txt = getText(n) || n.getAttribute('title');
//                         if (txt) {
//                             txt.split(',').forEach(f => {
//                                 const clean = f.trim();
//                                 if (clean && !freebies.includes(clean)) freebies.push(clean);
//                             });
//                         }
//                     });

//                     // ── Location ──────────────────────────────────────────────────────────
//                     const locEl = queryFirst(card,
//                         '[class*="upS4"]',            // keep old class as a try
//                         '[class*="location"]', '[class*="address"]',
//                         '[class*="neighborhood"]', '[class*="district"]',
//                         '[data-testid*="location"]', '[aria-label*="location"]'
//                     );
//                     const location = getText(locEl);

//                     if (extractedPrice) {
//                         collected.push({
//                             source: "dom_hotel_listing",
//                             title: name,
//                             price: extractedPrice,
//                             score,
//                             stars,
//                             provider,
//                             freebies,
//                             location
//                         });
//                     }
//                 } catch (e) { console.error('Hotel card parse error', e); }
//             });
//             return collected;
//         }
//     };

//     try {
//         let scraped = [];
//         let pageType = 'other';

//         if (url.includes('/flights/')) {
//             pageType = 'flight_results';
//             scraped.push(...Scraper.flightListings());
//         } else if (url.includes('/cars/')) {
//             pageType = 'car_results';
//             scraped.push(...Scraper.carListings());
//         } else if (url.includes('/hotels/')) {
//             pageType = 'hotel_results';
//             scraped.push(...Scraper.hotelListings());
//         }

//         const antiBotStatus = document.body.innerText.toLowerCase().includes('challenge-running')
//             ? 'blocked_cloudflare' : 'clear';
//         const activeFilters = Scraper.filters();
//         const urlData = Scraper.urlMetadata();

//         scraped.forEach(item => {
//             results.push({ ...item, ...activeFilters, ...urlData, pageType, antiBotStatus });
//         });
//     } catch (e) { console.error("Kayak Scraper failed", e); }

//     return results;
// })();
