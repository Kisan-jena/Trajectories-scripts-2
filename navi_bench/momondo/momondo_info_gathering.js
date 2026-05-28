(() => {
    const results = [];
    const url = window.location.href;

    // Helper: Safely extract text
    const getText = (el) => {
        if (!el) return null;
        let text = el.innerText || el.textContent || '';
        return text.replace(/\u00A0/g, ' ').trim().replace(/\s+/g, ' ');
    };

    const Parsers = {
        price: (text) => {
            if (!text) return null;
            // Match common currency symbols followed by a number
            let match = text.match(/([$€£₹]|rs\.?|inr|usd)?\s*([\d,]+(?:\.\d+)?)/i);
            if (match && match[2]) {
                let amount = parseFloat(match[2].replace(/,/g, ""));
                let symbol = (match[1] || "").toLowerCase();
                
                // USD is the base currency — no conversion needed for $
                // Convert other currencies TO USD if they appear
                if (symbol === '€') amount *= 1.08;        // EUR → USD
                else if (symbol === '£') amount *= 1.27;   // GBP → USD
                else if (symbol === '₹' || symbol === 'rs' || symbol === 'rs.' || symbol === 'inr') {
                    amount /= 83.0;                         // INR → USD
                }
                // $ and 'usd' pass through as-is (already in USD)
                
                return Math.round(amount * 100) / 100; // round to 2 decimal places
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
        flightListings: () => {
            const collected = [];
            const rows = document.querySelectorAll('div[role="group"][aria-label^="Result item"], .nrc6-wrapper');

            rows.forEach(row => {
                try {
                    const rowText = getText(row);
                    if (!rowText) return;

                    const priceNode = row.querySelector('[class*="price-text"], [data-test-id="price"], .price');
                    const extractedPrice = Parsers.price(priceNode ? getText(priceNode) : rowText);
                    if (!extractedPrice) return; 

                    let departTime = null;
                    let arrivalTime = null;
                    const timeMatch = rowText.match(/(\d{1,2}:\d{2})\s*[-–\u2013\u2014]\s*(\d{1,2}:\d{2})/);
                    if (timeMatch) {
                        departTime = timeMatch[1];
                        arrivalTime = timeMatch[2];
                    }

                    const airlineNode = row.querySelector('[class*="operator-text"], .codeshares-airline-names, [class*="name-only-text"]');
                    let airlineText = airlineNode ? getText(airlineNode) : '';
                    if (!airlineText) {
                        const logos = row.querySelectorAll('img[alt]');
                        const alts = [];
                        logos.forEach(img => {
                            const alt = (img.getAttribute('alt') || '').trim();
                            if (alt && alt.length > 2 && !alt.toLowerCase().includes("logo")) alts.push(alt);
                        });
                        if (alts.length > 0) airlineText = [...new Set(alts)].join(', '); 
                    }

                    let extractedStops = Parsers.stops(rowText);
                    let cabinText = '';
                    const cabinNode = row.querySelector('[aria-label*="Cabin"], [class*="cabin"]');
                    if (cabinNode) cabinText = getText(cabinNode);
                    if (!cabinText) {
                        const matchCabin = rowText.match(/(premium economy|first class|business class|business|economy)/i);
                        if (matchCabin) cabinText = matchCabin[1];
                    }

                    collected.push({
                        source: "dom_flight_listing",
                        airline: airlineText.toLowerCase(),
                        price: extractedPrice,
                        stops: extractedStops,
                        departTime,
                        arrivalTime,
                        cabinClass: cabinText.toLowerCase()
                    });
                } catch (e) { console.error("Error parsing flight row:", e); }
            });

            const unique = [];
            const seen = new Set();
            collected.forEach(item => {
                const key = `${item.price}-${item.departTime}-${item.arrivalTime}-${item.airline}`;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            });
            return unique;
        },

        hotelListings: () => {
            const collected = [];
            const rows = document.querySelectorAll('.S0Ps, .yuAt[role="group"][aria-label]');
            const processedElements = new Set();

            rows.forEach(row => {
                const container = row.closest('.S0Ps') || row;
                if (processedElements.has(container)) return;
                processedElements.add(container);

                try {
                    let name = '';
                    const nameEl = container.querySelector('.c9Hnq-big-name');
                    if (nameEl) name = getText(nameEl);
                    
                    if (!name) {
                        const groupEl = container.querySelector('[role="group"][aria-label]') || container;
                        name = groupEl.getAttribute('aria-label');
                    }
                    
                    if (!name || name.includes('Result item') || name === 'Search results') return;

                    let extractedPrice = null;
                    const priceNode = container.querySelector('[data-target="price"], .c1XBO');
                    if (priceNode) {
                        extractedPrice = Parsers.price(getText(priceNode));
                    }
                    if (!extractedPrice) return; 

                    let score = null;
                    const scoreNode = container.querySelector('.c9kNN');
                    if (scoreNode) {
                        const match = getText(scoreNode).match(/[\d.]+/);
                        if (match) score = parseFloat(match[0]);
                    }

                    let stars = null;
                    const starsNode = container.querySelector('.hEI8');
                    if (starsNode) {
                        const starMatch = getText(starsNode).match(/(\d+)/);
                        if (starMatch) stars = parseInt(starMatch[1], 10);
                    }
                    if (!stars) {
                        const starIcons = container.querySelectorAll('.O3Yc-star');
                        if (starIcons && starIcons.length > 0) stars = starIcons.length;
                    }

                    let provider = 'Unknown';
                    const providerImg = container.querySelector('.afsH-provider-logo, [class*="provider-logo"]');
                    if (providerImg && providerImg.getAttribute('alt')) {
                        provider = providerImg.getAttribute('alt').replace('.com', '').trim();
                    }

                    const freebies = [];
                    const freebieNodes = container.querySelectorAll('.BNDX');
                    freebieNodes.forEach(f => {
                        const text = getText(f);
                        if (text) freebies.push(text);
                    });

                    if (freebies.length === 0) {
                        const rawText = getText(container);
                        if (/free breakfast/i.test(rawText)) freebies.push('Free breakfast');
                        if (/free cancellation/i.test(rawText)) freebies.push('Free cancellation');
                    }

                    collected.push({
                        source: "dom_hotel_listing",
                        title: name,
                        price: extractedPrice,
                        score: score,
                        stars: stars,
                        provider: provider,
                        freebies: freebies
                    });

                } catch (e) { console.error("Error parsing hotel row:", e); }
            });

            const unique = [];
            const seen = new Set();
            collected.forEach(item => {
                const key = `${item.title}-${item.price}`;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            });
            return unique;
        },

        carListings: () => {
            const collected = [];
            // Target the main car result wrapper
            const rows = document.querySelectorAll('.jo6g-car-result-item');

            rows.forEach(row => {
                try {
                    // 1. Car Name and Category
                    let title = 'Unknown Car';
                    let category = '';
                    const titleNode = row.querySelector('.js-title');
                    if (titleNode) title = getText(titleNode);
                    
                    const subTitleNode = row.querySelector('.MseY-sub-title');
                    if (subTitleNode) {
                        const rawCategory = getText(subTitleNode);
                        category = rawCategory.replace(/or similar/i, '').trim();
                        // Sometimes the category is just "View deal for more details", ignore it
                        if (category.toLowerCase().includes('view deal')) category = '';
                    }

                    // 2. Price
                    let extractedPrice = null;
                    const priceNode = row.querySelector('.c4nz8-price-total, [aria-label*="total"]');
                    if (priceNode) {
                        extractedPrice = Parsers.price(getText(priceNode));
                    }
                    if (!extractedPrice) return; // Skip if no valid price

                    // 3. Booking Provider / Agency
                    let provider = 'Unknown Provider';
                    const providerNode = row.querySelector('.EuxN-provider-name');
                    if (providerNode) {
                        provider = getText(providerNode);
                    } else {
                        // Fallback to the provider image alt tag
                        const providerImg = row.querySelector('.EuxN-provider-logo');
                        if (providerImg && providerImg.getAttribute('alt')) {
                            provider = providerImg.getAttribute('alt').replace('Provider:', '').trim();
                        }
                    }

                    let agency = 'Unknown Agency';
                    const agencyImg = row.querySelector('.mR2O-agency-logo');
                    if (agencyImg && agencyImg.getAttribute('alt')) {
                        agency = agencyImg.getAttribute('alt').replace('Car agency:', '').trim();
                    }

                    // 4. Passenger capacity (Find the list item that says "Passengers count")
                    let passengers = null;
                    const passNode = row.querySelector('[aria-label="Passengers count"]');
                    if (passNode) {
                        const passText = getText(passNode);
                        if (passText) passengers = parseInt(passText, 10);
                    }

                    collected.push({
                        source: "dom_car_listing",
                        title: title,
                        category: category.toLowerCase(),
                        price: extractedPrice,
                        provider: provider,
                        agency: agency,
                        passengers: passengers
                    });

                } catch (e) {
                    console.error("Error parsing car row:", e);
                }
            });

            // Deduplicate based on Title, Provider, and Price
            const unique = [];
            const seen = new Set();
            collected.forEach(item => {
                const key = `${item.title}-${item.provider}-${item.price}`;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            });
            return unique;
        },

        urlMetadata: () => {
            let meta = {};
            if (url.includes('/flights/') || url.includes('/flight-search/')) {
                const match = url.match(/\/(?:flights|flight-search)\/([A-Za-z]{3})-([A-Za-z]{3})\/(\d{4}-\d{2}-\d{2})/i);
                if (match) meta = { origin: match[1], destination: match[2], departDate: match[3] };
            } else if (url.includes('/cars/') || url.includes('/car-search/')) {
                const match = url.match(/\/(?:cars|car-search)\/([^\/]+)\/([^\/]+)\/(\d{4}-\d{2}-\d{2})/i);
                if (match) meta = { pickUpLocation: match[1], dropOffLocation: match[2], pickUpDate: match[3] };
            } else if (url.includes('/hotels/') || url.includes('/hotel-search/')) {
                const match = url.match(/\/(?:hotels|hotel-search)\/([^\/]+)(?:\/(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2}))?/i);
                if (match) meta = { city: match[1], checkIn: match[2] || null, checkOut: match[3] || null };
            }
            return meta;
        },

        filters: () => {
            const f = { 
                filterAirlines: [], 
                filterStops: [], 
                filterMaxPrice: null,
                filterFreebies: [],
                filterMinStars: null,
                filterMinScore: null
            };
            
            const isFlight = url.includes('/flights/') || url.includes('/flight-search/');
            const isHotel = url.includes('/hotels/') || url.includes('/hotel-search/');
            
            if (!isFlight && !isHotel) return f; 
            
            try {
                // 1. Shared Max Price Logic
                const priceRegion = document.querySelector('div[role="region"][aria-label="Price"]');
                if (priceRegion) {
                    const resetBtn = priceRegion.querySelector('[class*="filters-reset"]');
                    const isResetHidden = resetBtn && (resetBtn.className.includes('hidden') || resetBtn.getAttribute('aria-disabled') === 'true');
                    
                    if (isHotel || !isResetHidden) {
                        const maxSlider = priceRegion.querySelector('[role="slider"][aria-label*="Max"], [role="slider"]:nth-child(2), [role="slider"]');
                        if (maxSlider) {
                            let valueText = maxSlider.getAttribute('aria-valuetext') || maxSlider.getAttribute('aria-valuenow');
                            const val = Parsers.price(valueText);
                            if (val) f.filterMaxPrice = val;
                        }
                    }
                }

                // 2. Flight Specific Logic
                if (isFlight) {
                    const getActiveFlightFilters = (regionLabel) => {
                        const labels = [];
                        const region = document.querySelector(`div[role="region"][aria-label="${regionLabel}"]`);
                        if (!region) return labels;

                        const resetBtn = region.querySelector('[class*="filters-reset"]');
                        if (resetBtn && (resetBtn.className.includes('hidden') || resetBtn.getAttribute('aria-disabled') === 'true')) {
                            return labels; 
                        }

                        const checkboxes = region.querySelectorAll('input[type="checkbox"]:checked');
                        checkboxes.forEach(cb => {
                            let text = '';
                            if (cb.id) {
                                const labelEl = document.querySelector(`label[for="${cb.id}"]`);
                                if (labelEl) text = getText(labelEl);
                            }
                            if (!text) {
                                const outer = cb.closest('[class*="checkbox-outer"]');
                                if (outer) text = getText(outer);
                            }
                            if (text) labels.push(text.trim());
                        });
                        return labels;
                    };

                    f.filterAirlines = getActiveFlightFilters("Airlines");
                    f.filterStops = getActiveFlightFilters("Stops");
                }

                // 3. Hotel Specific Logic
                if (isHotel) {
                    const activeChips = document.querySelectorAll('div[role="checkbox"][aria-checked="true"].IAhs-chip');
                    activeChips.forEach(chip => {
                        const text = getText(chip);
                        if (text) f.filterFreebies.push(text);
                    });

                    const classRegion = document.querySelector('div[role="region"][aria-label="Hotel class"], #stars');
                    if (classRegion) {
                        const activeClass = classRegion.querySelector('.HNDy-active .HNDy-label');
                        if (activeClass) {
                            const text = getText(activeClass);
                            const match = text.match(/(\d)/); 
                            if (match) f.filterMinStars = parseInt(match[1], 10);
                        }
                    }

                    const scoreRegion = document.querySelector('div[role="region"][aria-label="Review Score"], #extendedrating');
                    if (scoreRegion) {
                        const activeScore = scoreRegion.querySelector('.HNDy-active .HNDy-label');
                        if (activeScore) {
                            const text = getText(activeScore);
                            const match = text.match(/(\d)/); 
                            if (match && parseInt(match[1], 10) > 0) f.filterMinScore = parseFloat(match[1]);
                        }
                    }
                }
            } catch(e) { console.error("Momondo Filter parse error", e); }
            return f;
        }
    };

    try {
        let scraped = [];
        let pageType = 'other';

        if (url.includes('/flights/') || url.includes('/flight-search/')) {
            pageType = 'flight_results';
            scraped.push(...Scraper.flightListings());
        } else if (url.includes('/cars/') || url.includes('/car-search/')) {
            pageType = 'car_results';
            scraped.push(...Scraper.carListings());
        } else if (url.includes('/hotels/') || url.includes('/hotel-search/')) {
            pageType = 'hotel_results';
            scraped.push(...Scraper.hotelListings());
        }

        const antiBotStatus = document.body.innerText.toLowerCase().includes('challenge-running') ? 'blocked_cloudflare' : 'clear';
        const activeFilters = Scraper.filters();
        const urlData = Scraper.urlMetadata();

        scraped.forEach(item => {
            results.push({ ...item, ...activeFilters, ...urlData, pageType, antiBotStatus });
        });
    } catch (e) { console.error("Momondo Scraper failed", e); }

    return results;
})();