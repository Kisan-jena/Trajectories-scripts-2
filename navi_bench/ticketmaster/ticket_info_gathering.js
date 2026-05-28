(() => {
    const results = [];
    const url = window.location.href;
    const pageText = document.body ? document.body.innerText.toLowerCase() : '';

    // ============================================================================
    // 1. UTILITIES
    // ============================================================================

    const getText = (el) => el?.textContent?.trim().replace(/\s+/g, ' ') || null;
    
    const extractByPattern = (text, patterns) => {
        if (!text) return null;
        for (const regex of Object.values(patterns)) {
            try {
                const match = text.match(regex);
                if (match) return match[1] || match[0];
            } catch (e) { continue; }
        }
        return null;
    };

    // ============================================================================
    // 2. PARSERS (Adapted for Ticketmaster formats)
    // ============================================================================

    const Parsers = {
        price: (text) => {
            try {
                if (!text) return null;
                
                // Specifically hunt for currency symbols to avoid accidentally grabbing Section/Row numbers
                let match = text.match(/(?:[$£€₹]|USD|EUR|GBP|INR)\s*([\d,]+(?:\.\d{2})?)/i);
                if (match) return parseFloat(match[1].replace(/,/g, ""));
                
                // Fallback for Euro formatting (1.234,56)
                match = text.match(/(?:[$£€₹]|USD|EUR|GBP|INR)\s*([\d.]+(?:,\d{2})?)/i);
                if (match) return parseFloat(match[1].replace(/\./g, "").replace(",", "."));

                // Fallback for clean strings passed directly from slider inputs
                let clean = text.replace(/[₹€£$]/g, '').replace(/^(INR|USD|EUR|GBP)\s*/i, '').replace(/ea\./i, '').replace(/ea/i, '').replace(/\+/g, '').trim();
                match = clean.match(/^([\d,]+(?:\.\d{2})?)$/);
                if (match) return parseFloat(match[1].replace(/,/g, ""));
                
            } catch (e) { return null; }
            return null;
        },

        ticketCount: (text) => {
            try {
                if (!text) return null;
                // TM dropdowns or text often say "2 Tickets"
                return parseInt(text.match(/(\d+)\s*ticket/i)?.[1] || text.match(/^(\d+)$/)?.[1]);
            } catch (e) { return null; }
        },

        date: (text) => {
            try {
                if (!text) return null;
                const clean = text.toLowerCase().trim();
                
                // ISO format YYYY-MM-DD
                let match = clean.match(/(\d{4})-(\d{2})-(\d{2})/);
                if (match) return match[0];
                
                // TM format: "Sat • Oct 24, 2026" or "July 11, 2026"
                match = clean.match(/(?:[a-z]+[\s,]*[•\-|·]?\s*)?([a-z]{3})[a-z]*\s+(\d{1,2}),?\s*(\d{4})/i);
                if (match) {
                    const months = { jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12 };
                    const m = months[match[1].substring(0, 3)];
                    if (m) return `${match[3]}-${String(m).padStart(2,'0')}-${match[2].padStart(2,'0')}`;
                }

                // TM format missing year: "Sat • Jul 11"
                match = clean.match(/(?:[a-z]+[\s,]*[•\-|·]?\s*)?([a-z]{3})[a-z]*\s+(\d{1,2})/i);
                if (match) {
                    const months = { jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12 };
                    const m = months[match[1].substring(0, 3)];
                    const currentYear = new Date().getFullYear(); // Assume current year if missing
                    if (m) return `${currentYear}-${String(m).padStart(2,'0')}-${match[2].padStart(2,'0')}`;
                }
            } catch (e) { return null; }
            return null;
        },

        time: (text) => {
            try {
                if (!text) return null;
                const match = text.match(/(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
                if (match) {
                    let h = parseInt(match[1]);
                    if (match[3]?.toUpperCase() === 'PM' && h < 12) h += 12;
                    if (match[3]?.toUpperCase() === 'AM' && h === 12) h = 0;
                    return `${String(h).padStart(2, '0')}:${match[2]}`;
                }
            } catch (e) { return null; }
            return null;
        }
    };

    // ============================================================================
    // 3. ENRICHMENT HELPERS
    // ============================================================================

    const Enrichment = {
        pageType: () => {
            if (url.includes('/checkout')) return 'checkout';
            if (url.includes('queue') || pageText.includes('you are now in line')) return 'queue';
            if (url.includes('/event/')) return 'event_listing';
            if (url.includes('/search') || url.includes('/discover')) return 'search_results';
            if (url.includes('/artist/') || url.includes('/venue/')) return 'event_category';
            return 'other';
        },
        antiBotStatus: () => {
            if (pageText.includes('pardon the interruption') || document.querySelector('#sec-text-container')) return 'blocked_perimeterx';
            if (pageText.includes('sit tight') || url.includes('queue-it.net')) return 'queue_it';
            return 'clear';
        },
        category: () => {
            if (url.includes('sports')) return 'sports';
            if (url.includes('concerts') || url.includes('music')) return 'concerts';
            if (url.includes('arts-theater') || url.includes('theater')) return 'theater';
            if (url.includes('comedy')) return 'comedy';
            if (url.includes('family')) return 'family';
            return null;
        },
        status: (t) => {
            const s = (t || pageText).toLowerCase();
            if (s.includes('sold out') || s.includes('no tickets match')) return 'sold_out';
            if (s.includes('on sale date and time')) return 'future_sale';
            if (s.includes('presale happens') || s.includes('unlock')) return 'presale';
            if (Enrichment.pageType() === 'queue') return 'queue';
            return 'available';
        },
        isResale: (t) => /verified resale/i.test(t),
        obstructed: (t) => /obstructed|limited view|possible obstruction/i.test(t),
    };

    // ============================================================================
    // 4. SCRAPERS
    // ============================================================================

    const Scraper = {

        pageFilters: () => {
            try {
                // --- EVENT LISTING PAGE FILTERS ---
                // 1. Grab Quantity Dropdown
                const qtySelect = document.querySelector('select[data-bdd="mobileQtyDropdown"], #filter-bar-quantity');
                const selectedQuantity = qtySelect ? parseInt(qtySelect.value) : null;

                // 2. Grab Min Price
                const minInput = document.querySelector('[data-bdd="exposed-mobile-filter-price-slider-min"] input');
                const minSlider = document.querySelector('[aria-label*="Minimum ticket price"]');
                let minPriceText = minInput ? minInput.value : (minSlider ? minSlider.getAttribute('aria-valuenow') : null);
                
                // 3. Grab Max Price
                const maxInput = document.querySelector('[data-bdd="exposed-mobile-filter-price-slider-max"] input');
                const maxSlider = document.querySelector('[aria-label*="Maximum ticket price"]');
                let maxPriceText = maxInput ? maxInput.value : (maxSlider ? maxSlider.getAttribute('aria-valuenow') : null);

                // 4. Grab Ticket Types (Standard, Resale, VIP)
                const activeTicketTypes = [];
                const typeCheckboxes = document.querySelectorAll('input[type="checkbox"][data-bdd="filter-modal-checkbox"]');
                typeCheckboxes.forEach(cb => {
                    if (cb.checked) {
                        const testId = cb.getAttribute('data-testid') || '';
                        const val = cb.value || '';
                        if (/resale/i.test(testId) || /resale/i.test(val)) {
                            activeTicketTypes.push('resale');
                        } else if (/vip/i.test(testId) || /vip/i.test(val)) {
                            activeTicketTypes.push('vip');
                        } else {
                            activeTicketTypes.push('standard');
                        }
                    }
                });

                // 5. Grab ADA / Accessible Seating Toggle
                const adaToggle = document.querySelector('button[data-bdd="filter-ada-toggle"], button[data-testid="filter-ada-toggle"]');
                const isADAActive = adaToggle ? adaToggle.getAttribute('aria-checked') === 'true' : false;

                // --- SEARCH / DISCOVERY PAGE FILTERS ---
                // 6. Location Filter
                const locInput = document.querySelector('input[placeholder*="City"], input[placeholder*="Zip"]');
                const filterLocation = locInput ? locInput.value : null;

                // 7. Date Range Filter (Extract from hidden accessibility span)
                const dateSpans = Array.from(document.querySelectorAll('span[class*="VisuallyHidden"]'));
                const dateHidden = dateSpans.find(s => s.textContent.includes('Current date range:'));
                let filterDateRange = null;
                if (dateHidden) {
                    filterDateRange = dateHidden.textContent.replace(/.*Current date range:\s*/i, '').trim();
                } else {
                    // Fallback to label sibling
                    const dateLabel = Array.from(document.querySelectorAll('label')).find(l => l.textContent.trim() === 'Dates');
                    if (dateLabel && dateLabel.nextElementSibling) filterDateRange = getText(dateLabel.nextElementSibling);
                }

                // 8. Games / Event Type Dropdown (Home/Away/All)
                let filterGameType = null;
                const gameLabel = Array.from(document.querySelectorAll('label')).find(l => l.textContent.trim().includes('Games'));
                if (gameLabel && gameLabel.nextElementSibling) {
                    const gameSelect = gameLabel.nextElementSibling.querySelector('select');
                    if (gameSelect) filterGameType = gameSelect.options[gameSelect.selectedIndex]?.text;
                }

                return {
                    filterQuantity: selectedQuantity,
                    filterMinPrice: Parsers.price(minPriceText),
                    filterMaxPrice: Parsers.price(maxPriceText),
                    filterTicketTypes: activeTicketTypes.length > 0 ? activeTicketTypes : null,
                    filterADA: isADAActive,
                    filterLocation: filterLocation,
                    filterDateRange: filterDateRange,
                    filterGameType: filterGameType
                };
            } catch (e) { 
                return {}; 
            }
        },


        ldJson: () => {
            try {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                const found = [];
                for (const s of scripts) {
                    try {
                        const data = JSON.parse(s.textContent);
                        const graph = data["@graph"] || (Array.isArray(data) ? data : [data]);
                        for (const item of graph) {
                            const types = Array.isArray(item["@type"]) ? item["@type"] : [item["@type"] || ""];
                            if (!types.some(t => t.toLowerCase().includes("event"))) continue;
                            found.push({
                                source: "ld+json",
                                eventName: item.name?.toLowerCase(),
                                eventCategory: types[0],
                                date: item.startDate?.split("T")[0],
                                time: item.startDate?.split("T")[1]?.substring(0, 5),
                                venue: item.location?.name,
                                city: item.location?.address?.addressLocality?.toLowerCase(),
                                floorPrice: item.offers?.lowPrice ? parseFloat(item.offers.lowPrice) : null,
                                price: null, // FIX: Schema floor price is not a specific ticket price
                                currency: item.offers?.priceCurrency || "USD",
                                isResale: false, // LD+JSON schema doesn't distinguish resale vs primary
                                availabilityStatus: item.offers?.availability?.includes("InStock") ? "available" : "sold_out",
                                url: item.url || url
                            });
                        }
                    } catch (e) {}
                }
                return found;
            } catch (e) { return []; }
        },

        ticketListings: () => {
            const collected = [];
            let eventNameContext = "";
            
            try {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                    const data = JSON.parse(s.textContent);
                    const graph = data["@graph"] || [data];
                    const ev = graph.find(i => (Array.isArray(i["@type"]) ? i["@type"] : [i["@type"] || ""]).some(t=>t.toLowerCase().includes("event")));
                    if (ev && ev.name) { eventNameContext = ev.name; break; }
                }
            } catch(e){}

            if (!eventNameContext) {
                const header = document.querySelector('[data-testid="event-detail-header"] h1, [data-testid="event-detail-header"] h6, h1');
                eventNameContext = getText(header) || "";
            }

            if (!eventNameContext) {
                const match = url.match(/\/([a-z0-9-]+)-tickets/i);
                if (match) eventNameContext = match[1].replace(/-/g, ' ');
            }

            const rows = document.querySelectorAll(
                '#list-view li, ' +
                'li[role="menuitem"], ' +
                'li[data-bdd*="quick-picks-list-item"], ' +
                'li[data-price], ' +
                'li[data-bdd*="list-item-primary"], ' +
                'li[aria-label*="Sec"], ' +
                '[data-testid="offer-card"], ' +
                'div[class*="ticket-card"], ' +
                '[role="listitem"]'
            );

            rows.forEach(row => {
                try {
                    const rowText = getText(row);
                    if (!rowText) return;

                    const listingId = row.getAttribute('data-listing-id') || row.getAttribute('data-index');
                    const rawPrice = row.getAttribute('data-price');
                    const isSold = row.getAttribute('data-is-sold') === "1";

                    const priceNode = row.querySelector('[data-bdd="quick-pick-price-button"], [class*="price"], span[class*="Price"]');
                    const priceText = priceNode ? getText(priceNode) : null;
                    const extractedPrice = Parsers.price(rawPrice) || Parsers.price(priceText) || Parsers.price(rowText);

                    if (!extractedPrice) return;

                    // Aggregate all hidden accessibility text and visible tags to guarantee we find the section/row
                    const hiddenTextNodes = Array.from(row.querySelectorAll('[class*="VisuallyHidden"]')).map(n => n.textContent).join(' ');
                    const descNode = row.querySelector('[data-bdd="quick-pick-item-desc"], [class*="description"], [class*="Section"]');
                    const descText = (descNode ? (descNode.getAttribute('aria-label') || getText(descNode)) : "") + " " + hiddenTextNodes + " " + rowText;

                    const isResaleBranding = row.querySelector('[data-bdd*="resale-branding"]');
                    const typeNode = row.querySelector('[data-bdd="branding-ticket-text"]');
                    const typeText = typeNode ? getText(typeNode) : rowText;
                    
                    let ticketType = 'standard';
                    if (isResaleBranding || /Verified Resale/i.test(typeText) || /resale/i.test(rowText)) {
                        ticketType = 'resale';
                    } else if (/VIP/i.test(typeText) || /VIP/i.test(rowText)) {
                        ticketType = 'vip';
                    }

                    collected.push({
                        source: "dom_ticket_listing",
                        listingId: listingId,
                        eventName: eventNameContext.toLowerCase(), 
                        price: extractedPrice,
                        // FIXED: Added word boundaries (\b) so "Sec" doesn't partially match "Section"
                        section: extractByPattern(descText, {s: /(?:\bSection\b|\bSec\b)\s+([A-Za-z0-9\s]+?)(?=\s*(?:[•·,:-]|\bRow\b|$))/i}),
                        row: extractByPattern(descText, {r: /\bRow\s+([A-Za-z0-9]+)/i}),
                        seat: extractByPattern(rowText, {st: /\bSeats?\s*([\d\-,\s]+)/i}),
                        isVIP: ticketType === 'vip',
                        isParkingPass: /parking/i.test(rowText),
                        ticketType: ticketType,
                        availabilityStatus: isSold ? 'sold_out' : 'available',
                        info: rowText
                    });
                } catch (e) { console.error('Ticket row parse error', e); }
            });
            
            return collected;
        },

        eventCards: () => {
            const collected = [];
            // Target event cards on search/discover pages
            document.querySelectorAll('a[href*="/event/"], [data-testid="event-list-item"]').forEach(card => {
                try {
                    const text = getText(card);
                    if (!text || text.length < 10) return;
                    
                    const href = card.tagName === 'A' ? card.getAttribute('href') : card.querySelector('a')?.getAttribute('href');

                    let eventName = getText(card.querySelector('h3, [data-testid="event-title"]'));
                    if (!eventName && href) {
                         const match = href.match(/\/event\/([a-z0-9]+)/i);
                         if (!match) return; // Skip if it's not a valid event link
                         eventName = card.textContent.trim().split('\n')[0].trim().toLowerCase(); // Fallback to first line of text
                    }

                    // Extract venue and city from event card text.
                    // TM event cards commonly show: "VenueName · City, ST" or "VenueName - City, ST"
                    let venue = null;
                    let city = null;
                    const venueEl = card.querySelector('[data-testid="event-venue"], [class*="venue"], [class*="Venue"]');
                    if (venueEl) {
                        venue = getText(venueEl);
                    }
                    const locEl = card.querySelector('[data-testid="event-location"], [class*="location"], [class*="Location"]');
                    if (locEl) {
                        city = getText(locEl);
                    }
                    // Fallback: parse from the full card text using common separator patterns
                    if (!venue || !city) {
                        const locMatch = text.match(/([^·•\-\n]+?)\s*[·•\-]\s*([A-Za-z .'-]+),\s*([A-Z]{2})/);
                        if (locMatch) {
                            if (!venue) venue = locMatch[1].trim();
                            if (!city) city = locMatch[2].trim().toLowerCase();
                        }
                    }

                    if (eventName) {
                        collected.push({
                            source: "dom_event_card",
                            url: href || url,
                            eventName: eventName.toLowerCase(),
                            venue: venue,
                            city: city ? city.toLowerCase() : null,
                            date: Parsers.date(text),
                            availabilityStatus: text.toLowerCase().includes('canceled') ? 'cancelled' : 'available',
                            info: text
                        });
                    }
                } catch (e) { }
            });
            return collected;
        },

        checkout: () => {
            if (!url.includes('checkout')) return [];
            const collected = [];
            try {
                // TM checkout has an order summary panel
                const summaryPanel = document.querySelector('[data-testid="order-summary"], [class*="order-summary"]');
                if (summaryPanel) {
                    const text = getText(summaryPanel);
                    const eventName = getText(document.querySelector('h1, [data-testid="event-name"]'));
                    
                    collected.push({
                        source: "checkout_summary",
                        eventName: eventName?.toLowerCase(),
                        price: Parsers.price(text),
                        ticketCount: Parsers.ticketCount(text),
                        date: Parsers.date(text),
                        info: "checkout_page",
                        availabilityStatus: "available"
                    });
                }
            } catch (e) {}
            return collected;
        }
    };

    // ============================================================================
    // 5. MAIN EXECUTION
    // ============================================================================

    try {
        let scraped = [];

        if (url.includes('checkout')) {
            scraped.push(...Scraper.checkout());
        }
        scraped.push(...Scraper.ldJson());
        scraped.push(...Scraper.ticketListings());
        scraped.push(...Scraper.eventCards());

        // Fallback for empty pages (like queues or blocked pages)
        if (scraped.length === 0) {
            scraped.push({
                source: "fallback_metadata",
                url: url,
                eventName: getText(document.querySelector('h1'))?.toLowerCase() || 'unknown',
                info: "No specific elements found. Check antiBot state."
            });
        }

        // 1. Find the global date/time (Borrow from LD+JSON if available, otherwise parse the Header)
        const ldJsonItem = scraped.find(i => i.source === 'ld+json' && i.date);
        const headerEl = document.querySelector('#edp-event-header, [data-bdd="event-header"]');
        const headerText = headerEl ? getText(headerEl) : pageText;
        
        const globalDate = ldJsonItem ? ldJsonItem.date : Parsers.date(headerText);
        const globalTime = ldJsonItem ? ldJsonItem.time : Parsers.time(headerText);
        const filters = Scraper.pageFilters();

        // FIX: Check if ANY resale tickets are actively displayed in the list
        const hasResaleListings = Array.from(document.querySelectorAll('li[data-price], #list-view li, div[class*="ticket-card"], [role="listitem"]'))
            .some(row => /verified resale/i.test(getText(row) || ''));

        const meta = {
            pageType: Enrichment.pageType(),
            antiBotStatus: Enrichment.antiBotStatus(),
            eventCategory: Enrichment.category(),
            globalStatus: Enrichment.status(pageText),
            globalDate: globalDate,
            globalTime: globalTime,
            hasResaleListings: hasResaleListings,
            ...filters // Inject the scraped filters here
        };

        const seen = new Set();
        
        scraped.forEach(item => {
            const key = `${item.eventName}-${item.date || 'nodate'}-${item.section || 'nosection'}-${item.row || 'norow'}-${item.seat || 'noseat'}-${item.listingId || 'noid'}-${item.price || 'noprice'}-${item.source}`;
            if (!seen.has(key)) {
                seen.add(key);
                
                let finalStatus = item.availabilityStatus;
                if (!finalStatus || finalStatus === 'available') {
                    if (meta.globalStatus === 'sold_out' || meta.globalStatus === 'queue' || meta.globalStatus === 'presale') {
                        finalStatus = meta.globalStatus;
                    }
                }

                // INHERITANCE FIX: Only force the global date if we are on an actual event page.
                // Otherwise, keep the distinct dates for individual event cards on search pages.
                let finalDate = item.date;
                let finalTime = item.time;
                if (!finalDate && (meta.pageType === 'event_listing' || meta.pageType === 'checkout')) {
                    finalDate = meta.globalDate;
                    finalTime = meta.globalTime;
                }

                results.push({
                    ...item,
                    ...meta,
                    // FIX: Prioritize the item's scraped category (LD+JSON) over the URL-based meta category
                    eventCategory: item.eventCategory || meta.eventCategory,
                    date: finalDate,
                    parsedTime: Parsers.time(finalTime || ''),
                    availabilityStatus: finalStatus,
                    isResale: item.isResale !== undefined ? item.isResale : Enrichment.isResale(item.info),
                    obstructedView: Enrichment.obstructed(item.info),
                });
            }
        });

    } catch (e) {
        console.error("Ticketmaster Scraper failed", e);
    }

    return results;
})();