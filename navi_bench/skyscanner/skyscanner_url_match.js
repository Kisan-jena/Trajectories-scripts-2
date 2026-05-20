/**
 * Skyscanner Info Gathering — Comprehensive DOM Scraper
 *
 * Injected into Skyscanner pages via page.evaluate() to extract:
 * 1. LD+JSON structured data (flights, hotels, FAQPage, BreadcrumbList)
 * 2. Full flight result listings (price, airline, stops, times, duration)
 * 3. Full hotel result listings (name, price, star rating, review score)
 * 4. Full car hire result listings (car name, category, price, supplier, specs)
 * 5. DOM filter state (sort tabs, sidebar filters, active checkboxes)
 * 6. Meta tags (og:title, og:url, description, canonical)
 * 7. Anti-bot detection (captcha, challenge pages)
 * 8. URL metadata parsing
 *
 * Returns an array of InfoDict objects for the Python verifier.
 *
 * Browser-verified against skyscanner.net (Mar 2026)
 *
 * Last updated: 2026-03-26
 */
(() => {
    'use strict';

    const results = [];
    const url = window.location.href;
    const pageText = document.body ? document.body.innerText.toLowerCase() : '';

    // ============================================================================
    // 1. UTILITIES
    // ============================================================================

    const getText = (el) => {
        if (!el) return null;
        let text = el.innerText || el.textContent || '';
        return text.replace(/\u00A0/g, ' ').trim().replace(/\s+/g, ' ');
    };

    const getAttr = (selector, attr) => {
        const el = document.querySelector(selector);
        return el ? (el.getAttribute(attr) || '') : '';
    };

    const getMeta = (name) => {
        return getAttr(`meta[name="${name}"], meta[property="${name}"]`, 'content') || '';
    };

    // ============================================================================
    // 2. PARSERS
    // ============================================================================

    const Parsers = {
        /**
         * Extract price from text, handling multiple currency formats.
         * Skyscanner shows prices in local currency (₹, $, €, £, etc.)
         */
        price: (text) => {
            if (!text) return null;
            try {
                // Match currency symbol + amount: $150, €89, ₹12,345, £200
                let match = text.match(/(?:[$€£₹¥]|rs\.?|inr|usd|eur|gbp)\s*([\d,]+(?:\.\d+)?)/i);
                if (match) return parseFloat(match[1].replace(/,/g, ''));

                // Match amount + currency: 150 USD, 89 EUR
                match = text.match(/([\d,]+(?:\.\d+)?)\s*(?:[$€£₹¥]|rs\.?|inr|usd|eur|gbp)/i);
                if (match) return parseFloat(match[1].replace(/,/g, ''));

                // Fallback: just a number in price context
                match = text.match(/(\d[\d,]*(?:\.\d{2})?)/);
                if (match) return parseFloat(match[1].replace(/,/g, ''));
            } catch (e) { return null; }
            return null;
        },

        /**
         * Parse stops from text (e.g., "direct", "1 stop", "2 stops").
         */
        stops: (text) => {
            if (!text) return null;
            if (/\bdirect\b|\bnonstop\b|\bnon-stop\b/i.test(text)) return 0;
            const match = text.match(/(\d+)\s*stops?/i);
            if (match) return parseInt(match[1]);
            return null;
        },

        /**
         * Parse duration from text (e.g., "5h 30m", "2h", "45m").
         */
        duration: (text) => {
            if (!text) return null;
            const match = text.match(/(\d+)\s*h(?:\s*(\d+)\s*m)?/i);
            if (match) {
                const hours = parseInt(match[1]);
                const minutes = match[2] ? parseInt(match[2]) : 0;
                return hours * 60 + minutes;
            }
            const minOnly = text.match(/(\d+)\s*m(?:in)?/i);
            if (minOnly) return parseInt(minOnly[1]);
            return null;
        },

        /**
         * Parse time from text. Handles 12-hour AM/PM and 24-hour formats.
         * IMPORTANT: 12-hour AM/PM must be checked FIRST — the bare HH:MM regex
         * would otherwise match "2:30" inside "2:30 PM" and return "02:30"
         * instead of the correct "14:30".
         */
        time: (text) => {
            if (!text) return null;
            // Check 12-hour AM/PM first (e.g. "2:30 PM" → "14:30")
            let match = text.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
            if (match) {
                let h = parseInt(match[1]);
                if (match[3].toUpperCase() === 'PM' && h < 12) h += 12;
                if (match[3].toUpperCase() === 'AM' && h === 12) h = 0;
                return `${String(h).padStart(2, '0')}:${match[2]}`;
            }
            // Fallback: 24-hour format (e.g. "14:30" → "14:30")
            match = text.match(/(\d{1,2}):(\d{2})/);
            if (match) return `${match[1].padStart(2, '0')}:${match[2]}`;
            return null;
        },

        /**
         * Parse star rating from text.
         */
        stars: (text) => {
            if (!text) return null;
            const match = text.match(/(\d(?:\.\d)?)\s*(?:star|★)/i);
            if (match) return parseFloat(match[1]);
            return null;
        },

        /**
         * Parse review score from text.
         * Skyscanner uses a 1–5 scale (e.g., "4.5 / 5", "Excellent 4.3").
         * Returns the score on the NATIVE 0–5 scale.
         * If a /10 format is encountered (partner data), normalizes to 0–5.
         */
        reviewScore: (text) => {
            if (!text) return null;
            // Match "X / 5" (Skyscanner's native scale)
            const match5 = text.match(/(\d+(?:\.\d+)?)\s*\/\s*5/);
            if (match5) return parseFloat(match5[1]);
            // Match "X / 10" (partner/legacy data) — normalize to 5-scale
            const match10 = text.match(/(\d+(?:\.\d+)?)\s*\/\s*10/);
            if (match10) return parseFloat(match10[1]) / 2;
            // Fallback: raw number with optional label (e.g., "Excellent 4.3")
            const match2 = text.match(/(?:exceptional|excellent|very good|good|okay|poor)?\s*(\d+(?:\.\d+)?)/i);
            if (match2) {
                const score = parseFloat(match2[1]);
                // If score <= 5, assume native 5-point scale
                if (score <= 5) return score;
                // If score <= 10, assume 10-point and normalize
                if (score <= 10) return score / 2;
            }
            return null;
        }
    };

    // ============================================================================
    // 3. ENRICHMENT HELPERS
    // ============================================================================

    const Enrichment = {
        pageType: () => {
            if (url.includes('/transport/d/')) return 'multicity';
            if (url.includes('/transport/flights-from/')) return 'browse';
            if (url.includes('/transport/flights/')) return 'flights';
            if (url.includes('/hotels/search')) return 'hotel_results';
            if (url.includes('/hotels/')) return 'hotels';
            if (url.includes('/carhire/results/')) return 'carhire_results';
            if (url.includes('/carhire/')) return 'carhire';
            return 'other';
        },

        antiBotStatus: () => {
            if (pageText.includes('press & hold')) return 'blocked_captcha';
            if (pageText.includes('are you a person or a robot')) return 'blocked_captcha';
            if (pageText.includes('challenge-running')) return 'blocked_cloudflare';
            if (pageText.includes('just a moment')) return 'blocked_cloudflare';
            if (pageText.includes('verify you are human')) return 'blocked_captcha';
            if (pageText.includes('checking your browser')) return 'blocked_cloudflare';
            if (pageText.includes('security check')) return 'blocked_security';
            if (pageText.includes('access denied')) return 'blocked_access';
            if (document.querySelector('#challenge-running')) return 'blocked_cloudflare';
            if (document.querySelector('.cf-browser-verification')) return 'blocked_cloudflare';
            return 'clear';
        },

        urlMetadata: () => {
            const meta = {};
            try {
                // Flight URL
                const flightMatch = url.match(/\/transport\/flights\/([a-z]{2,5})\/([a-z]{2,5})\/(\d{6})(?:\/(\d{6}))?/i);
                if (flightMatch) {
                    meta.origin = flightMatch[1].toLowerCase();
                    meta.destination = flightMatch[2].toLowerCase();
                    meta.departDate = flightMatch[3];
                    if (flightMatch[4]) meta.returnDate = flightMatch[4];
                }

                // Hotel URL
                const urlObj = new URL(url);
                if (url.includes('/hotels/')) {
                    meta.entityId = urlObj.searchParams.get('entity_id') || '';
                    meta.checkin = urlObj.searchParams.get('checkin') || '';
                    meta.checkout = urlObj.searchParams.get('checkout') || '';
                    meta.adults = urlObj.searchParams.get('adults') || '';
                    meta.rooms = urlObj.searchParams.get('rooms') || '';
                    meta.sort = urlObj.searchParams.get('sort') || '';
                }

                // Car hire URL
                const carMatch = url.match(/\/carhire\/results\/([^/]+)\/([^/]+)\/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?:\/(\d+))?/i);
                if (carMatch) {
                    meta.pickupLocation = carMatch[1];
                    meta.dropoffLocation = carMatch[2];
                    meta.pickupDatetime = carMatch[3];
                    meta.dropoffDatetime = carMatch[4];
                    if (carMatch[5]) meta.driverAge = carMatch[5];
                }

                // Flight query params
                ['adultsv2', 'childrenv2', 'cabinclass', 'rtn', 'stops', 'airlines', 'alliances', 'preferdirects'].forEach(key => {
                    const val = urlObj.searchParams.get(key);
                    if (val) meta[key] = val;
                });

            } catch (e) { console.error('URL metadata parse error', e); }
            return meta;
        }
    };

    // ============================================================================
    // 4. LD+JSON EXTRACTION
    // ============================================================================

    const LdJson = {
        /**
         * Extract all LD+JSON structured data from the page.
         */
        extractAll: () => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            const items = [];
            scripts.forEach(script => {
                try {
                    const data = JSON.parse(script.textContent);
                    if (Array.isArray(data)) {
                        items.push(...data);
                    } else if (data['@graph']) {
                        items.push(...data['@graph']);
                    } else {
                        items.push(data);
                    }
                } catch (e) { /* skip invalid JSON */ }
            });
            return items;
        },

        /**
         * Extract flight offers from LD+JSON.
         * Skyscanner may embed FlightReservation, Offer, or custom structured data.
         */
        extractFlightOffers: (items) => {
            const offers = [];
            for (const item of items) {
                if (!item) continue;
                const type = item['@type'] || '';

                // FlightReservation schema
                if (type === 'FlightReservation' || type === 'Flight') {
                    offers.push({
                        source: 'ld+json_flight',
                        type: type,
                        name: item.name || '',
                        departureAirport: item.departureAirport?.iataCode || item.departureAirport?.name || '',
                        arrivalAirport: item.arrivalAirport?.iataCode || item.arrivalAirport?.name || '',
                        departureTime: item.departureTime || '',
                        arrivalTime: item.arrivalTime || '',
                        airline: item.provider?.name || item.airline?.name || '',
                        flightNumber: item.flightNumber || '',
                    });
                }

                // Offer / Product (aggregate flight offers)
                if (type === 'Offer' || type === 'Product') {
                    offers.push({
                        source: 'ld+json_offer',
                        type: type,
                        name: item.name || '',
                        price: item.price ? parseFloat(item.price) : null,
                        priceCurrency: item.priceCurrency || '',
                        url: item.url || '',
                    });
                }

                // AggregateOffer (for fare ranges)
                if (type === 'AggregateOffer') {
                    offers.push({
                        source: 'ld+json_aggregate',
                        type: type,
                        lowPrice: item.lowPrice ? parseFloat(item.lowPrice) : null,
                        highPrice: item.highPrice ? parseFloat(item.highPrice) : null,
                        priceCurrency: item.priceCurrency || '',
                        offerCount: item.offerCount || null,
                    });
                }
            }
            return offers;
        },

        /**
         * Extract hotel data from LD+JSON.
         */
        extractHotelData: (items) => {
            const hotels = [];
            for (const item of items) {
                if (!item) continue;
                const type = item['@type'] || '';

                if (type === 'Hotel' || type === 'LodgingBusiness' || type === 'Hostel') {
                    hotels.push({
                        source: 'ld+json_hotel',
                        type: type,
                        name: item.name || '',
                        starRating: item.starRating?.ratingValue || null,
                        aggregateRating: item.aggregateRating?.ratingValue || null,
                        reviewCount: item.aggregateRating?.reviewCount || null,
                        address: item.address?.streetAddress || '',
                        city: item.address?.addressLocality || '',
                        country: item.address?.addressCountry || '',
                        priceRange: item.priceRange || '',
                        image: item.image || '',
                    });
                }
            }
            return hotels;
        },

        /**
         * Extract FAQ data from LD+JSON.
         */
        extractFAQ: (items) => {
            const faqs = [];
            for (const item of items) {
                if (!item || item['@type'] !== 'FAQPage') continue;
                const entities = item.mainEntity || [];
                (Array.isArray(entities) ? entities : [entities]).forEach(q => {
                    if (q['@type'] === 'Question') {
                        faqs.push({
                            question: q.name || '',
                            answer: q.acceptedAnswer?.text || '',
                        });
                    }
                });
            }
            return faqs;
        },

        /**
         * Extract breadcrumb navigation from LD+JSON.
         */
        extractBreadcrumbs: (items) => {
            for (const item of items) {
                if (!item || item['@type'] !== 'BreadcrumbList') continue;
                const elements = item.itemListElement || [];
                return elements.map(e => ({
                    position: e.position,
                    name: e.name || e.item?.name || '',
                    url: e.item?.['@id'] || e.item || '',
                }));
            }
            return [];
        }
    };

    // ============================================================================
    // 5. DOM LISTING SCRAPERS
    // ============================================================================

    const Scraper = {
        /**
         * Scrape flight result listings from the DOM.
         * Skyscanner renders flight cards with itinerary legs, prices, and airlines.
         */
        flightListings: () => {
            const collected = [];
            try {
                // Method 1: data-testid based cards (most reliable)
                const cards = document.querySelectorAll(
                    '[data-testid="result-item"], ' +
                    'a[class*="ItineraryResult"], ' +
                    'div[class*="FlightsResults"] > div, ' +
                    'div[class*="ResultsSummary"] a, ' +
                    '[class*="itinerary-result"]'
                );

                cards.forEach(card => {
                    try {
                        const cardText = getText(card) || '';
                        if (!cardText || cardText.length < 10) return;

                        // Price
                        const priceNode = card.querySelector(
                            '[class*="price"], [class*="Price"], ' +
                            'span[class*="amount"], [data-testid*="price"]'
                        );
                        const price = Parsers.price(priceNode ? getText(priceNode) : cardText);

                        // Airline
                        const airlineNode = card.querySelector(
                            '[class*="carrier"], [class*="Carrier"], ' +
                            '[class*="airline"], [class*="Airline"], ' +
                            '[class*="operator"], img[alt]'
                        );
                        let airline = '';
                        if (airlineNode) {
                            airline = getText(airlineNode) || airlineNode.getAttribute('alt') || '';
                        }

                        // Stops
                        const stops = Parsers.stops(cardText);

                        // Duration
                        const durationNode = card.querySelector(
                            '[class*="duration"], [class*="Duration"]'
                        );
                        const duration = Parsers.duration(
                            durationNode ? getText(durationNode) : cardText
                        );

                        // Times (departure → arrival)
                        const timeNodes = card.querySelectorAll(
                            '[class*="time"], [class*="Time"], ' +
                            'time, [class*="departure"], [class*="arrival"]'
                        );
                        let departTime = null, arrivalTime = null;
                        if (timeNodes.length >= 2) {
                            departTime = Parsers.time(getText(timeNodes[0]));
                            arrivalTime = Parsers.time(getText(timeNodes[timeNodes.length - 1]));
                        }
                        // Fallback: regex from card text
                        if (!departTime) {
                            const timeMatch = cardText.match(/(\d{1,2}:\d{2})\s*[–\-→]\s*(\d{1,2}:\d{2})/);
                            if (timeMatch) {
                                departTime = timeMatch[1];
                                arrivalTime = timeMatch[2];
                            }
                        }

                        // Cabin class from card
                        let cabin = '';
                        if (/premium economy/i.test(cardText)) cabin = 'premiumeconomy';
                        else if (/business/i.test(cardText)) cabin = 'business';
                        else if (/first class/i.test(cardText)) cabin = 'first';
                        else if (/economy/i.test(cardText)) cabin = 'economy';

                        // Layover airports
                        const layoverNodes = card.querySelectorAll('[class*="stop-info"], [class*="layover"]');
                        const layovers = [];
                        layoverNodes.forEach(n => {
                            const t = getText(n);
                            if (t) layovers.push(t);
                        });

                        if (price) {
                            collected.push({
                                source: 'dom_flight_listing',
                                airline: airline.toLowerCase(),
                                price: price,
                                stops: stops,
                                duration: duration,
                                departTime: departTime,
                                arrivalTime: arrivalTime,
                                cabin: cabin,
                                layovers: layovers,
                                info: cardText.substring(0, 300),
                            });
                        }
                    } catch (e) { /* skip bad card */ }
                });

                // Method 2: Fallback — generic approach for any result row
                if (collected.length === 0) {
                    const allLinks = document.querySelectorAll('a[href*="transport/flights"]');
                    allLinks.forEach(link => {
                        const text = getText(link);
                        const price = Parsers.price(text);
                        if (price && text && text.length > 20) {
                            collected.push({
                                source: 'dom_flight_link',
                                price: price,
                                stops: Parsers.stops(text),
                                duration: Parsers.duration(text),
                                info: text.substring(0, 300),
                            });
                        }
                    });
                }
            } catch (e) { console.error('Flight listing scraper error', e); }
            return collected;
        },

        /**
         * Scrape hotel result listings from the DOM.
         */
        hotelListings: () => {
            const collected = [];
            try {
                const cards = document.querySelectorAll(
                    '[data-testid="hotel-card"], ' +
                    'a[class*="HotelCard"], ' +
                    'div[class*="HotelResult"], ' +
                    '[class*="hotel-card"], ' +
                    '[class*="PropertyCard"]'
                );

                cards.forEach(card => {
                    try {
                        const cardText = getText(card) || '';
                        if (!cardText || cardText.length < 10) return;

                        // Hotel name
                        const nameNode = card.querySelector(
                            'h2, h3, [class*="hotel-name"], [class*="HotelName"], ' +
                            '[data-testid="hotel-name"], [class*="PropertyName"]'
                        );
                        const name = nameNode ? getText(nameNode) : '';

                        // Price
                        const priceNode = card.querySelector(
                            '[class*="price"], [class*="Price"], ' +
                            '[data-testid*="price"]'
                        );
                        const price = Parsers.price(priceNode ? getText(priceNode) : cardText);

                        // Star rating
                        const starsNode = card.querySelector(
                            '[class*="star"], [class*="Star"], ' +
                            '[aria-label*="star"], [data-testid*="star"]'
                        );
                        const stars = starsNode ?
                            (Parsers.stars(getText(starsNode)) ||
                             Parsers.stars(starsNode.getAttribute('aria-label'))) : null;

                        // Review score
                        const scoreNode = card.querySelector(
                            '[class*="review"], [class*="Review"], ' +
                            '[class*="rating"], [class*="Rating"], ' +
                            '[data-testid*="rating"]'
                        );
                        const reviewScore = scoreNode ? Parsers.reviewScore(getText(scoreNode)) : null;

                        // Location / Area
                        const locationNode = card.querySelector(
                            '[class*="location"], [class*="Location"], ' +
                            '[class*="distance"], [class*="Distance"]'
                        );
                        const location = locationNode ? getText(locationNode) : '';

                        // Provider
                        const providerNode = card.querySelector(
                            '[class*="provider"], [class*="Provider"], ' +
                            'img[alt*="booking"], img[alt*="hotels"], img[alt*="expedia"]'
                        );
                        let provider = '';
                        if (providerNode) {
                            provider = getText(providerNode) || providerNode.getAttribute('alt') || '';
                        }

                        // Amenities / Tags
                        const tags = [];
                        card.querySelectorAll('[class*="tag"], [class*="Tag"], [class*="amenity"], [class*="badge"]').forEach(t => {
                            const text = getText(t);
                            if (text && text.length < 50) tags.push(text);
                        });

                        if (name || price) {
                            collected.push({
                                source: 'dom_hotel_listing',
                                name: name,
                                price: price,
                                stars: stars,
                                reviewScore: reviewScore,
                                location: location,
                                provider: provider.toLowerCase(),
                                tags: tags,
                                info: cardText.substring(0, 300),
                            });
                        }
                    } catch (e) { /* skip bad card */ }
                });
            } catch (e) { console.error('Hotel listing scraper error', e); }
            return collected;
        },

        /**
         * Scrape car hire result listings from the DOM.
         */
        carHireListings: () => {
            const collected = [];
            try {
                const cards = document.querySelectorAll(
                    '[data-testid="car-card"], ' +
                    'div[class*="CarResult"], ' +
                    '[class*="car-card"], ' +
                    '[class*="VehicleCard"], ' +
                    'a[class*="CarCard"]'
                );

                cards.forEach(card => {
                    try {
                        const cardText = getText(card) || '';
                        if (!cardText || cardText.length < 10) return;

                        // Car name / model
                        const nameNode = card.querySelector(
                            'h2, h3, [class*="car-name"], [class*="CarName"], ' +
                            '[class*="vehicle-name"], [class*="VehicleName"]'
                        );
                        const name = nameNode ? getText(nameNode) : '';

                        // Category (Small, Medium, Large, SUV, etc.)
                        const categoryNode = card.querySelector(
                            '[class*="category"], [class*="Category"], ' +
                            '[class*="vehicle-type"], [class*="VehicleType"]'
                        );
                        const category = categoryNode ? getText(categoryNode) : '';

                        // Price
                        const priceNode = card.querySelector(
                            '[class*="price"], [class*="Price"], ' +
                            '[data-testid*="price"]'
                        );
                        const price = Parsers.price(priceNode ? getText(priceNode) : cardText);

                        // Supplier / Provider
                        const supplierNode = card.querySelector(
                            '[class*="supplier"], [class*="Supplier"], ' +
                            '[class*="provider"], [class*="Provider"], ' +
                            'img[alt*="rental"], img[class*="supplier"]'
                        );
                        let supplier = '';
                        if (supplierNode) {
                            supplier = getText(supplierNode) || supplierNode.getAttribute('alt') || '';
                        }

                        // Transmission (Automatic / Manual)
                        let transmission = null;
                        if (/\bautomatic\b/i.test(cardText)) transmission = 'automatic';
                        else if (/\bmanual\b/i.test(cardText)) transmission = 'manual';

                        // Specs (passengers, bags, doors)
                        let passengers = null, bags = null, doors = null;
                        const specNodes = card.querySelectorAll(
                            '[class*="spec"], [class*="Spec"], ' +
                            '[class*="feature"], [class*="Feature"], ' +
                            '[aria-label], [role="listitem"]'
                        );
                        specNodes.forEach(s => {
                            const text = getText(s) || '';
                            const aria = s.getAttribute('aria-label') || '';
                            const combined = text + ' ' + aria;
                            if (/passenger|seat/i.test(combined)) {
                                const m = combined.match(/(\d+)/);
                                if (m) passengers = parseInt(m[1]);
                            }
                            if (/bag|luggage|suitcase/i.test(combined)) {
                                const m = combined.match(/(\d+)/);
                                if (m) bags = parseInt(m[1]);
                            }
                            if (/door/i.test(combined)) {
                                const m = combined.match(/(\d+)/);
                                if (m) doors = parseInt(m[1]);
                            }
                        });

                        if (name || price) {
                            collected.push({
                                source: 'dom_carhire_listing',
                                name: name,
                                category: category,
                                price: price,
                                supplier: supplier.toLowerCase(),
                                transmission: transmission,
                                passengers: passengers,
                                bags: bags,
                                doors: doors,
                                info: cardText.substring(0, 300),
                            });
                        }
                    } catch (e) { /* skip bad card */ }
                });
            } catch (e) { console.error('Car hire listing scraper error', e); }
            return collected;
        },

        /**
         * Extract active sort tab and all filter state from the DOM.
         */
        filterState: () => {
            const state = {
                activeSort: null,
                activeSortTabs: [],
                // Flight filters
                flightStopFilters: [],
                flightAirlineFilters: [],
                flightAllianceFilters: [],
                flightTimeFilters: [],
                // Car hire filters
                carTransmission: [],
                carType: [],
                carSuppliers: [],
                // Hotel filters
                hotelStarRating: [],
                hotelSort: null,
                hotelPropertyType: [],
                // Generic
                filterSections: [],
                priceRange: null,
            };

            try {
                // ── Sort tabs (flights) ──
                // Method 1: aria-selected tabs
                const sortTabs = document.querySelectorAll(
                    '[role="tab"], [data-testid*="sort"], button[class*="SortTab"], ' +
                    '[class*="SortButton"], [class*="sort-tab"]'
                );
                sortTabs.forEach(tab => {
                    const text = getText(tab);
                    if (text && (
                        tab.getAttribute('aria-selected') === 'true' ||
                        tab.classList.contains('active') ||
                        tab.classList.contains('selected') ||
                        (tab.hasAttribute('aria-pressed') && tab.getAttribute('aria-pressed') === 'true')
                    )) {
                        state.activeSortTabs.push(text.toLowerCase());
                    }
                });

                // Method 2: Highlighted sort button (Best/Cheapest/Fastest)
                if (state.activeSortTabs.length === 0) {
                    document.querySelectorAll('button').forEach(btn => {
                        const text = getText(btn);
                        if (text && /^(best|cheapest|fastest|quickest|direct|recommended)$/i.test(text)) {
                            const computed = window.getComputedStyle(btn);
                            const bgColor = computed.backgroundColor;
                            const fontWeight = computed.fontWeight;
                            if (
                                (bgColor && bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'transparent') ||
                                (fontWeight && parseInt(fontWeight) >= 600)
                            ) {
                                state.activeSortTabs.push(text.toLowerCase());
                            }
                        }
                    });
                }

                if (state.activeSortTabs.length > 0) {
                    state.activeSort = state.activeSortTabs[0];
                }

                // ── Enumerate filter sections ──
                document.querySelectorAll(
                    '[class*="FilterSection"] h3, [class*="filter"] h3, ' +
                    '[data-testid*="filter"] h3, [class*="FilterSection"] h4, ' +
                    '[class*="filter"] h4, [class*="sidebar"] h3'
                ).forEach(h => {
                    const text = getText(h);
                    if (text) state.filterSections.push(text);
                });

                // ── Flight stop filters ──
                document.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
                    const parent = cb.closest('label') || cb.parentElement;
                    if (!parent) return;
                    const text = getText(parent) || '';
                    if (/\bdirect\b|\bnon-?stop\b|\b\d+\s*stop/i.test(text)) {
                        state.flightStopFilters.push(text.toLowerCase());
                    }
                    if (/airline/i.test(text)) {
                        state.flightAirlineFilters.push(text.toLowerCase());
                    }
                    if (/alliance/i.test(text) || /star alliance|oneworld|skyteam/i.test(text)) {
                        state.flightAllianceFilters.push(text.toLowerCase());
                    }
                    if (/automatic/i.test(text)) state.carTransmission.push('automatic');
                    if (/manual/i.test(text)) state.carTransmission.push('manual');
                    if (/\bstar\b/i.test(text) && /\d/.test(text)) {
                        const starMatch = text.match(/(\d)/);
                        if (starMatch) state.hotelStarRating.push(parseInt(starMatch[1]));
                    }
                });

                // ── Price slider / range ──
                const priceSlider = document.querySelector(
                    '[aria-label*="price"] input[type="range"], ' +
                    '[class*="price-slider"], [class*="PriceSlider"]'
                );
                if (priceSlider) {
                    state.priceRange = {
                        min: priceSlider.getAttribute('min'),
                        max: priceSlider.getAttribute('max'),
                        value: priceSlider.value,
                    };
                }

                // ── Hotel sort from DOM ──
                document.querySelectorAll(
                    '[class*="sort"] [aria-selected="true"], ' +
                    '[class*="Sort"] button[class*="active"]'
                ).forEach(opt => {
                    const text = getText(opt);
                    if (text) state.hotelSort = text.toLowerCase();
                });

            } catch (e) { console.error('Filter state extraction error', e); }
            return state;
        }
    };

    // ============================================================================
    // 6. MAIN EXECUTION
    // ============================================================================

    try {
        const pageType = Enrichment.pageType();
        const antiBotStatus = Enrichment.antiBotStatus();
        const urlMetadata = Enrichment.urlMetadata();
        const ldJsonItems = LdJson.extractAll();
        const filterState = Scraper.filterState();

        // Common fields for all results
        const commonFields = {
            url: url,
            pageType: pageType,
            title: document.title || '',
            h1: getText(document.querySelector('h1')),
            metaDescription: getMeta('description'),
            ogTitle: getMeta('og:title'),
            ogUrl: getMeta('og:url'),
            ogImage: getMeta('og:image'),
            canonical: getAttr('link[rel="canonical"]', 'href'),
            antiBotStatus: antiBotStatus,
            ...urlMetadata,
            source: 'skyscanner',
        };

        // ── LD+JSON Results ──
        const flightOffers = LdJson.extractFlightOffers(ldJsonItems);
        flightOffers.forEach(offer => {
            results.push({ ...commonFields, ...offer });
        });

        const hotelData = LdJson.extractHotelData(ldJsonItems);
        hotelData.forEach(hotel => {
            results.push({ ...commonFields, ...hotel });
        });

        const faqs = LdJson.extractFAQ(ldJsonItems);
        if (faqs.length > 0) {
            results.push({
                ...commonFields,
                source: 'ld+json_faq',
                faqs: faqs,
                faqCount: faqs.length,
            });
        }

        const breadcrumbs = LdJson.extractBreadcrumbs(ldJsonItems);
        if (breadcrumbs.length > 0) {
            results.push({
                ...commonFields,
                source: 'ld+json_breadcrumbs',
                breadcrumbs: breadcrumbs,
            });
        }

        // ── DOM Listing Results ──
        if (pageType === 'flights') {
            const flights = Scraper.flightListings();
            flights.forEach(flight => {
                results.push({ ...commonFields, ...flight, ...filterState });
            });

            // Aggregate summary
            if (flights.length > 0) {
                const prices = flights.map(f => f.price).filter(p => p != null);
                results.push({
                    ...commonFields,
                    source: 'dom_flight_summary',
                    totalResults: flights.length,
                    lowestPrice: prices.length > 0 ? Math.min(...prices) : null,
                    highestPrice: prices.length > 0 ? Math.max(...prices) : null,
                    avgPrice: prices.length > 0 ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length) : null,
                    airlines: [...new Set(flights.map(f => f.airline).filter(Boolean))],
                    ...filterState,
                });
            }
        }

        if (pageType === 'hotel_results' || pageType === 'hotels') {
            const hotels = Scraper.hotelListings();
            hotels.forEach(hotel => {
                results.push({ ...commonFields, ...hotel, ...filterState });
            });

            if (hotels.length > 0) {
                const prices = hotels.map(h => h.price).filter(p => p != null);
                results.push({
                    ...commonFields,
                    source: 'dom_hotel_summary',
                    totalResults: hotels.length,
                    lowestPrice: prices.length > 0 ? Math.min(...prices) : null,
                    highestPrice: prices.length > 0 ? Math.max(...prices) : null,
                    ...filterState,
                });
            }
        }

        if (pageType === 'carhire_results' || pageType === 'carhire') {
            const cars = Scraper.carHireListings();
            cars.forEach(car => {
                results.push({ ...commonFields, ...car, ...filterState });
            });

            if (cars.length > 0) {
                const prices = cars.map(c => c.price).filter(p => p != null);
                results.push({
                    ...commonFields,
                    source: 'dom_carhire_summary',
                    totalResults: cars.length,
                    lowestPrice: prices.length > 0 ? Math.min(...prices) : null,
                    highestPrice: prices.length > 0 ? Math.max(...prices) : null,
                    suppliers: [...new Set(cars.map(c => c.supplier).filter(Boolean))],
                    transmissions: [...new Set(cars.map(c => c.transmission).filter(Boolean))],
                    ...filterState,
                });
            }
        }

        // ── Fallback for empty pages ──
        if (results.length === 0) {
            results.push({
                ...commonFields,
                source: 'fallback_metadata',
                info: 'No specific elements found. Check antiBot status.',
                ...filterState,
            });
        }

    } catch (e) {
        console.error('Skyscanner Scraper failed', e);
        results.push({
            url: url,
            source: 'error',
            error: e.message || String(e),
            antiBotStatus: Enrichment.antiBotStatus(),
        });
    }

    return results;
})();
