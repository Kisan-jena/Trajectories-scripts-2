() => {
  const results = [];

  // DEBUG: Log page info
  console.log('[DEBUG JS] ============ SCRAPER START ============');
  console.log('[DEBUG JS] Page URL:', window.location.href);
  console.log('[DEBUG JS] Page Title:', document.title);

  const detectPageCurrency = () => {
    const headerCurrency = document.querySelector(
      '[data-testid="header-currency-picker-trigger"], [data-testid="currency-picker"]'
    );
    const headerText = headerCurrency ? headerCurrency.textContent || '' : '';
    if (/\bINR\b/i.test(headerText) || /₹/.test(headerText)) return 'INR';
    if (/\bUSD\b/i.test(headerText) || /\$/.test(headerText)) return 'USD';
    if (/\bEUR\b/i.test(headerText) || /€/.test(headerText)) return 'EUR';
    if (/\bGBP\b/i.test(headerText) || /£/.test(headerText)) return 'GBP';

    const bodyText = document.body ? document.body.innerText || '' : '';
    if (bodyText.includes('INR') || bodyText.includes('₹')) return 'INR';
    if (bodyText.includes('USD') || bodyText.includes('$')) return 'USD';
    if (bodyText.includes('EUR') || bodyText.includes('€')) return 'EUR';
    if (bodyText.includes('GBP') || bodyText.includes('£')) return 'GBP';
    return null;
  };

  const pageCurrency = detectPageCurrency();
  if (pageCurrency) {
    console.log('[DEBUG JS] Detected page currency:', pageCurrency);
  }

  const extractDecimalInRange = (text, min = 1, max = 10) => {
    if (!text) return null;
    const normalized = String(text).replace(/\s+/g, ' ').trim();
    const match = normalized.match(/(\d+(?:\.\d)?)(?:\s*\/\s*10)?/);
    if (!match) return null;
    const value = parseFloat(match[1]);
    if (isNaN(value) || value < min || value > max) return null;
    return value;
  };

  const extractRouteFromHeader = () => {
    const selectors = [
      '[data-testid="map-header"]',
      '[data-testid="route-header"]',
      '[data-testid="trip-title"]',
      'header h1',
      'h1',
      'h2',
    ];
    const arrow = '\u2192';

    const splitRouteText = (text) => {
      const normalized = String(text).replace(/\s+/g, ' ').trim();
      if (!normalized) return null;
      if (normalized.includes(arrow)) {
        const parts = normalized.split(arrow).map((p) => p.trim());
        if (parts.length >= 2) return { origin: parts[0], destination: parts[1] };
      }
      const lower = normalized.toLowerCase();
      const toIndex = lower.indexOf(' to ');
      if (toIndex > 0) {
        return {
          origin: normalized.slice(0, toIndex).trim(),
          destination: normalized.slice(toIndex + 4).trim(),
        };
      }
      const dashIndex = normalized.indexOf(' - ');
      if (dashIndex > 0) {
        return {
          origin: normalized.slice(0, dashIndex).trim(),
          destination: normalized.slice(dashIndex + 3).trim(),
        };
      }
      return null;
    };

    for (const selector of selectors) {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        const parsed = splitRouteText(el.textContent || '');
        if (parsed?.origin && parsed?.destination) return parsed;
      }
    }

    const titleParsed = splitRouteText(document.title || '');
    if (titleParsed?.origin && titleParsed?.destination) return titleParsed;

    return { origin: null, destination: null };
  };

  const routeFromPath = (() => {
    try {
      const parts = window.location.pathname.split('/').filter(Boolean);
      const mapIndex = parts.indexOf('map');
      if (mapIndex >= 0 && parts.length >= mapIndex + 3) {
        const normalize = (slug) =>
          decodeURIComponent(slug).replace(/-/g, ' ').trim();
        return {
          origin: normalize(parts[mapIndex + 1]),
          destination: normalize(parts[mapIndex + 2]),
        };
      }
    } catch (e) {
      console.warn('[DEBUG JS] Failed to parse route from URL:', e);
    }
    return { origin: null, destination: null };
  })();

  const routeFromPage = (() => {
    const headerRoute = extractRouteFromHeader();
    return {
      origin: headerRoute.origin || routeFromPath.origin,
      destination: headerRoute.destination || routeFromPath.destination,
    };
  })();

  const routeFromQuery = (() => {
    try {
      const url = new URL(window.location.href);
      const routeParam = url.searchParams.get('route');
      if (!routeParam) return null;
      const normalized = decodeURIComponent(routeParam)
        .replace(/[-_]+/g, ' ')
        .replace(/\bFly\b/gi, '')
        .trim();
      return normalized || null;
    } catch (e) {
      console.warn('[DEBUG JS] Failed to parse route query:', e);
      return null;
    }
  })();

  const extractScheduleRouteText = (card) => {
    const parts = [];

    if (routeFromPage.origin && routeFromPage.destination) {
      parts.push(`${routeFromPage.origin} to ${routeFromPage.destination}`);
    }

    if (routeFromQuery) {
      parts.push(routeFromQuery);
    }

    const cardText = card?.innerText || '';
    const lines = cardText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    const airportCandidates = lines.filter((line) => {
      if (/airport/i.test(line)) return true;
      if (/\b[A-Z]{3}\b/.test(line) && / - /.test(line)) return true;
      return false;
    });

    const uniqueAirports = [...new Set(airportCandidates)];
    if (uniqueAirports.length > 0) {
      parts.push(...uniqueAirports);
    }

    const text = parts.filter(Boolean).join(' | ');
    return text || null;
  };

  // ==========================================
  // 1. ROUTE CARDS (The main search page)
  // ==========================================
  const routeCards = document.querySelectorAll(
    '[data-testid^="trip-search-result"]'
  );
  console.log('[DEBUG JS] Route cards found:', routeCards.length);
  routeCards.forEach((card) => {
    try {
      const titleEl = card.querySelector('h1');
      const mode = titleEl ? titleEl.textContent.trim() : null;

      const timeEl = card.querySelector('time');
      let duration = null;
      if (timeEl) {
        const raw = timeEl.getAttribute('datetime');
        if (raw) {
          const hMatch = raw.match(/(\d+)H/);
          const mMatch = raw.match(/(\d+)M/);
          const hours = hMatch ? parseInt(hMatch[1], 10) : 0;
          const minutes = mMatch ? parseInt(mMatch[1], 10) : 0;
          duration = hours * 60 + minutes;
        }
      }

      const priceEl = card.querySelector('.text-text-brand');
      let min_price = null;
      let max_price = null;
      if (priceEl) {
        const text = priceEl.textContent.trim();
        const numbers = text.match(/[\d,]+/g);
        if (numbers && numbers.length > 0) {
          const values = numbers
            .map((n) => parseInt(n.replace(/,/g, ''), 10))
            .filter((n) => !isNaN(n));
          if (values.length > 0) {
            min_price = Math.min(...values);
            max_price = Math.max(...values);
          }
        }
      }

      results.push({
        mode,
        duration,
        min_price,
        max_price,
        pageType: 'results',
      });
    } catch (e) {
      console.error('Error parsing route card:', e);
    }
  });

  // ==========================================
  // 2. SCHEDULE CARDS (The flight details page)
  // ==========================================
  const scheduleCards = document.querySelectorAll(
    '[aria-labelledby^="schedule-cell-times-"]'
  );
  console.log('[DEBUG JS] Schedule cards found:', scheduleCards.length);
  scheduleCards.forEach((card) => {
    try {
      const airlineImgs = card.querySelectorAll('img[alt]');
      const airlines = Array.from(airlineImgs)
        .map((img) => img.alt.trim())
        .filter((alt) => alt);

      const uniqueAirlines = [...new Set(airlines)];
      const mode =
        uniqueAirlines.length > 0 ? uniqueAirlines.join(', ') : 'Flight';

      let duration = null;
      const timeEls = card.querySelectorAll('time');
      timeEls.forEach((timeEl) => {
        const raw = timeEl.getAttribute('datetime');
        if (raw && raw.startsWith('PT') && duration === null) {
          const hMatch = raw.match(/(\d+)H/);
          const mMatch = raw.match(/(\d+)M/);
          const hours = hMatch ? parseInt(hMatch[1], 10) : 0;
          const minutes = mMatch ? parseInt(mMatch[1], 10) : 0;
          duration = hours * 60 + minutes;
        }
      });

      let min_price = null;
      let max_price = null;
      const brandEls = card.querySelectorAll(
        '.text-text-brand, .text-label-xl.font-bold'
      );
      brandEls.forEach((el) => {
        const text = el.textContent || '';
        const numbers = text.match(/[\d,]+/g);
        if (numbers && numbers.length > 0) {
          const values = numbers
            .map((n) => parseInt(n.replace(/,/g, ''), 10))
            .filter((n) => !isNaN(n));
          if (values.length > 0) {
            const elMin = Math.min(...values);
            const elMax = Math.max(...values);
            if (min_price === null || elMin < min_price) min_price = elMin;
            if (max_price === null || elMax > max_price) max_price = elMax;
          }
        }
      });

      results.push({
        mode,
        duration,
        min_price,
        max_price,
        origin: routeFromPage.origin,
        destination: routeFromPage.destination,
        route_text: extractScheduleRouteText(card),
        pageType: 'schedule',
      });
    } catch (e) {
      console.error('Error parsing schedule card:', e);
    }
  });

  // ==========================================
  // 3. HOTEL CARDS (The accommodations page)
  // ==========================================
  console.log('[DEBUG JS] === HOTEL CARDS SECTION ===');

  // OLD LOGIC: Try original Rome2Rio selector first
  let hotelCards = document.querySelectorAll('[data-testid="hotel-list-item"]');
  console.log(
    '[DEBUG JS] Old selector \'[data-testid="hotel-list-item"]\' found:',
    hotelCards.length,
    'cards'
  );

  hotelCards.forEach((card) => {
    try {
      const nameEl = card.querySelector('h3');
      let name = nameEl ? nameEl.textContent.trim() : 'Unknown Hotel';

      let stars = null;
      const starsEl = card.querySelector(
        '[aria-label$="stars"], [data-testid*="rating-stars"]'
      );
      if (starsEl) {
        const match = starsEl.getAttribute('aria-label').match(/(\d+)/);
        if (match) stars = parseInt(match[1], 10);
      }

      if (!stars) {
        const starContainer = card.querySelector(
          '[data-testid="rating-stars"]'
        );
        if (starContainer) {
          const svgStars = starContainer.querySelectorAll('svg').length;
          if (svgStars > 0) stars = svgStars;
        }
      }

      if (stars && stars > 5) {
        if (stars <= 10 && stars % 2 === 0) stars = Math.round(stars / 2);
        else if (stars > 10 && stars <= 20 && stars % 2 === 0)
          stars = Math.round(stars / 2);
        else stars = Math.min(stars, 5);
      }

      const priceEl = card.querySelector('.text-heading-md');
      let min_price = null;
      let max_price = null;
      let currency = null;
      if (priceEl) {
        const text = priceEl.textContent.trim();
        const numbers = text.match(/[\d,]+/g);
        if (numbers && numbers.length > 0) {
          const val = parseInt(numbers[0].replace(/,/g, ''), 10);
          if (!isNaN(val)) {
            min_price = val;
            max_price = val;
          }
        }

        if (/\bINR\b|₹/i.test(text)) currency = 'INR';
        else if (/\bUSD\b|\$/i.test(text)) currency = 'USD';
        else if (/€/i.test(text)) currency = 'EUR';
        else if (/£/i.test(text)) currency = 'GBP';
      }

      if (min_price === null) {
        const priceNodes = card.querySelectorAll(
          '[data-testid*="price" i], [class*="price"], [aria-label*="price" i], [aria-label*="rate" i]'
        );
        const candidates = [];
        priceNodes.forEach((el) => {
          const text = (
            el.textContent ||
            el.getAttribute('aria-label') ||
            ''
          ).trim();
          const matches = text.match(/[\d,]+/g);
          if (matches && matches.length > 0) {
            matches.forEach((m) => {
              const val = parseInt(m.replace(/,/g, ''), 10);
              if (!isNaN(val)) candidates.push(val);
            });
          }
        });

        const cardText = card.textContent || '';
        const currencyMatches = cardText.match(
          /(?:USD|EUR|INR|GBP|AUD|CAD|₹|\$|€|£)\s*[\d,]+/gi
        );
        if (currencyMatches) {
          currencyMatches.forEach((m) => {
            const num = m.match(/[\d,]+/);
            if (num) {
              const val = parseInt(num[0].replace(/,/g, ''), 10);
              if (!isNaN(val)) candidates.push(val);
            }
            if (!currency) {
              if (/\bINR\b|₹/i.test(m)) currency = 'INR';
              else if (/\bUSD\b|\$/i.test(m)) currency = 'USD';
              else if (/€/i.test(m)) currency = 'EUR';
              else if (/£/i.test(m)) currency = 'GBP';
            }
          });
        }

        if (candidates.length > 0) {
          min_price = Math.min(...candidates);
          max_price = Math.max(...candidates);
        }
      }

      let score = null;
      let location_score = null;
      const scoreEl = card.querySelector(
        '[data-testid="review-score"], [data-testid="hotel-review-score"], [class*="reviewScore"], [class*="review-score"]'
      );
      if (scoreEl) {
        const scoreText = (
          scoreEl.getAttribute('aria-label') ||
          scoreEl.textContent ||
          ''
        ).trim();
        const scoreMatch = scoreText.match(/(\d+(?:\.\d)?)(?:\s*\/\s*10)?/);
        if (scoreMatch) {
          const scoreVal = parseFloat(scoreMatch[1]);
          if (!isNaN(scoreVal) && scoreVal >= 1 && scoreVal <= 10) {
            score = scoreVal;
          }
        }
      }
      if (score === null) {
        const scoreLabelEl = card.querySelector(
          '[aria-label*="rating" i], [aria-label*="review" i], [data-testid*="review" i]'
        );
        if (scoreLabelEl) {
          const labelText = (
            scoreLabelEl.getAttribute('aria-label') ||
            scoreLabelEl.textContent ||
            ''
          ).trim();
          const labelMatch = labelText.match(/(\d+(?:\.\d)?)(?:\s*\/\s*10)?/);
          if (labelMatch) {
            const v = parseFloat(labelMatch[1]);
            if (!isNaN(v) && v >= 1 && v <= 10) score = v;
          }
        }
      }
      if (score === null) {
        const cardText = (card.innerText || card.textContent || '')
          .replace(/\s+/g, ' ')
          .trim();
        const sentimentScoreMatch = cardText.match(
          /\b(very good|fabulous|exceptional|superb|wonderful|good)\b[^\d]{0,40}(\d+(?:\.\d)?)/i
        );
        if (sentimentScoreMatch) {
          const v = parseFloat(sentimentScoreMatch[2]);
          if (!isNaN(v) && v >= 1 && v <= 10) score = v;
        }
      }
      if (score === null) {
        const allTexts = Array.from(card.querySelectorAll('span, div'));
        for (const el of allTexts) {
          const t = el.textContent.trim();
          const m = t.match(/^(\d+(?:\.\d)?)\s*(?:\/\s*10)?$/);
          if (m) {
            const v = parseFloat(m[1]);
            if (v >= 5 && v <= 10 && el.children.length === 0) {
              score = v;
              break;
            }
          }
        }
      }
      if (score === null) {
        const cardText = (card.innerText || card.textContent || '')
          .replace(/\s+/g, ' ')
          .trim();
        const scoreMatch =
          cardText.match(/(\d+(?:\.\d)?)\s*\/\s*10/) ||
          cardText.match(
            /\b(very good|fabulous|exceptional|superb|wonderful|good)\b[^\d]{0,40}(\d+(?:\.\d)?)/i
          ) ||
          cardText.match(/score\s*[:\-]?\s*(\d+(?:\.\d)?)/i) ||
          cardText.match(/rating\s*[:\-]?\s*(\d+(?:\.\d)?)/i);
        if (scoreMatch) {
          const v = parseFloat(scoreMatch[2] || scoreMatch[1]);
          if (!isNaN(v) && v >= 1 && v <= 10) score = v;
        }
      }

      if (location_score === null) {
        const cardText = card.textContent || '';
        const locMatch =
          cardText.match(/Location\s*(\d+(?:\.\d)?)/i) ||
          cardText.match(/Location\s*score\s*(\d+(?:\.\d)?)/i);
        if (locMatch) {
          const v = parseFloat(locMatch[1]);
          if (!isNaN(v) && v >= 1 && v <= 10) location_score = v;
        }
      }

      console.log(
        '[DEBUG JS] OLD LOGIC Hotel found:',
        name,
        '| Stars:',
        stars,
        '| Price:',
        min_price,
        '| Score:',
        score
      );
      if (!currency && pageCurrency) currency = pageCurrency;

      results.push({
        mode: 'Hotel',
        name,
        stars,
        score,
        location_score,
        min_price,
        max_price,
        currency,
        pageType: 'hotels',
      });
    } catch (e) {
      console.error('Error parsing hotel card:', e);
    }
  });

  // NEW LOGIC: If old selector found nothing, try newer Booking.com structure
  if (hotelCards.length === 0) {
    console.log('[DEBUG JS] OLD LOGIC found 0 results, trying NEW LOGIC...');

    let newHotelCards = document.querySelectorAll(
      'div[data-testid*="property-card"], article[data-testid*="property"], div[class*="PropertyCard"], div[class*="Hotel-card"]'
    );
    console.log(
      '[DEBUG JS] NEW selector attempt 1 found:',
      newHotelCards.length,
      'cards'
    );

    // If still no results, try finding hotel items by searching for elements with property images and text
    if (newHotelCards.length === 0) {
      console.log(
        '[DEBUG JS] Attempt 1 failed, trying fallback pattern matching...'
      );
      const potentialCards = document.querySelectorAll(
        'div[role="region"], article, div[class*="card"]'
      );
      console.log('[DEBUG JS] Found potential cards:', potentialCards.length);
      const filteredCards = [];
      potentialCards.forEach((card) => {
        const text = card.textContent || '';
        // If the card contains hotel-like info: name, stars or rating, price info
        if (
          (text.match(/★|star/i) ||
            text.match(/exceptional|very good|good|fabulous/i)) &&
          text.match(/[\d,]+/) &&
          card.querySelector('img') &&
          card.querySelectorAll('button, a').length > 0
        ) {
          filteredCards.push(card);
        }
      });
      console.log(
        '[DEBUG JS] Filtered cards (after pattern matching):',
        filteredCards.length
      );
      if (filteredCards.length > 0) newHotelCards = filteredCards;
    }

    console.log(
      '[DEBUG JS] FINAL newHotelCards to process:',
      newHotelCards.length
    );

    newHotelCards.forEach((card) => {
      try {
        // Extract hotel name - try multiple selectors
        let nameEl = card.querySelector(
          'h3, h2, [data-testid="title"], [class*="hotel-name"], [class*="property-name"]'
        );
        let name = nameEl ? nameEl.textContent.trim() : null;

        // If no name found, try to extract from links
        if (!name) {
          const linkEl = card.querySelector(
            'a[href*="hotel"], a[data-testid="title-link"]'
          );
          if (linkEl) name = linkEl.textContent.trim();
        }

        if (name) {
          name = name
            .replace(/opens in new window/gi, '')
            .replace(/this property is unavailable[\s\S]*$/i, '')
            .trim();
        }

        // If still no name, skip this card
        if (!name) {
          console.log('[DEBUG JS] NEW LOGIC: Card skipped - no name found');
          return;
        }

        console.log('[DEBUG JS] NEW LOGIC: Processing hotel:', name);

        // Extract stars - try multiple methods
        let stars = null;

        // Method 1: Look for star elements in aria-label
        const starsEl = card.querySelector(
          '[aria-label*="star"], [title*="star"], [data-testid*="rating-stars"]'
        );
        if (starsEl) {
          const match = (
            starsEl.getAttribute('aria-label') ||
            starsEl.getAttribute('title') ||
            starsEl.textContent ||
            ''
          ).match(/(\d+)/);
          if (match) stars = parseInt(match[1], 10);
        }

        if (!stars) {
          const starContainer = card.querySelector(
            '[data-testid="rating-stars"]'
          );
          if (starContainer) {
            const svgStars = starContainer.querySelectorAll('svg').length;
            if (svgStars > 0) stars = svgStars;
          }
        }

        if (!stars) {
          const cardText = card.textContent || '';
          const starMatch = cardText.match(/(\d)\s*-?\s*star/i);
          if (starMatch) stars = parseInt(starMatch[1], 10);
        }

        if (stars && stars > 5) {
          if (stars <= 10 && stars % 2 === 0) stars = Math.round(stars / 2);
          else if (stars > 10 && stars <= 20 && stars % 2 === 0)
            stars = Math.round(stars / 2);
          else stars = Math.min(stars, 5);
        }

        // Method 2: Search for visual star indicators
        if (!stars) {
          const allElements = card.querySelectorAll('*');
          for (const el of allElements) {
            const attr =
              el.getAttribute('aria-label') || el.getAttribute('title') || '';
            const match = attr.match(/(\d+)\s*(?:out of|\/)\s*(\d+)\s*stars?/i);
            if (match) {
              stars = parseInt(match[1], 10);
              break;
            }
          }
        }

        // Extract price - try multiple selectors
        let min_price = null;
        let max_price = null;
        let currency = null;

        // Method 1: Look for price elements
        const priceSelectors = [
          '.text-heading-md',
          '[data-testid="price-and-discounted-price"]',
          '[data-testid="price-and-discounted-price"] *',
          '[class*="price"]',
          '[data-testid*="price"]',
          '[aria-label*="price"]',
          'span[class*="amount"]',
        ];

        let priceEl = null;
        for (const sel of priceSelectors) {
          priceEl = card.querySelector(sel);
          if (priceEl && priceEl.textContent.match(/[\d,]+/)) break;
        }

        if (priceEl) {
          const text = priceEl.textContent.trim();
          const numbers = text.match(/[\d,]+/g);
          if (numbers && numbers.length > 0) {
            const val = parseInt(numbers[0].replace(/,/g, ''), 10);
            if (!isNaN(val) && val > 0) {
              min_price = val;
              max_price = val;
            }
          }

          if (/\bINR\b|₹/i.test(text)) currency = 'INR';
          else if (/\bUSD\b|\$/i.test(text)) currency = 'USD';
          else if (/€/i.test(text)) currency = 'EUR';
          else if (/£/i.test(text)) currency = 'GBP';
        }

        // Method 2: Search entire card for currency + price patterns
        if (min_price === null) {
          const cardText = card.textContent || '';
          const currencyPatterns = [
            { code: 'USD', regex: /USD\s*[\d,]+/gi },
            { code: 'INR', regex: /₹\s*[\d,]+/gi },
            { code: 'EUR', regex: /€\s*[\d,]+/gi },
            { code: 'GBP', regex: /£\s*[\d,]+/gi },
            { code: 'USD', regex: /\$\s*[\d,]+/gi },
          ];

          const candidates = [];
          currencyPatterns.forEach((pattern) => {
            const matches = cardText.match(pattern.regex);
            if (matches) {
              matches.forEach((m) => {
                const nums = m.match(/[\d,]+/);
                if (nums) {
                  const val = parseInt(nums[0].replace(/,/g, ''), 10);
                  if (!isNaN(val) && val > 10 && val < 1000000)
                    candidates.push(val);
                  if (!currency) currency = pattern.code;
                }
              });
            }
          });

          if (candidates.length === 0) {
            // Also look for standalone numbers that might be prices
            const numberMatches = cardText.match(/[\d,]{3,}/g);
            if (numberMatches) {
              numberMatches.forEach((m) => {
                const val = parseInt(m.replace(/,/g, ''), 10);
                if (!isNaN(val) && val > 50 && val < 100000)
                  candidates.push(val);
              });
            }
          }

          if (candidates.length > 0) {
            const uniqueCandidates = [...new Set(candidates)];
            min_price = Math.min(...uniqueCandidates);
            max_price = Math.max(...uniqueCandidates);
          }
        }

        if (!currency && pageCurrency) currency = pageCurrency;

        // Extract score/rating
        let score = null;
        let location_score = null;

        // Method 1: Look for score elements
        const scoreSelectors = [
          '[data-testid="review-score"]',
          '[data-testid="review-score"] *',
          '[data-testid="hotel-review-score"], [class*="reviewScore"], [class*="review-score"]',
          '[class*="score"]',
          '[class*="rating"]',
          '[data-testid*="score"]',
          '[aria-label*="review"]',
        ];

        for (const sel of scoreSelectors) {
          const scoreEl = card.querySelector(sel);
          if (scoreEl) {
            const scoreText = (
              scoreEl.getAttribute('aria-label') ||
              scoreEl.textContent ||
              ''
            ).trim();
            const scoreVal = extractDecimalInRange(scoreText);
            if (scoreVal !== null) {
              score = scoreVal;
              break;
            }
          }
        }

        // Method 2: Search card text for score patterns
        if (score === null) {
          const cardText = card.textContent || '';
          const scoreMatch =
            cardText.match(/(\d+(?:\.\d)?)\s*(?:\/\s*10|out of 10)/i) ||
            cardText.match(/score\s*[:\-]?\s*(\d+(?:\.\d)?)/i) ||
            cardText.match(/rating\s*[:\-]?\s*(\d+(?:\.\d)?)/i);
          if (scoreMatch) {
            const v = extractDecimalInRange(scoreMatch[1]);
            if (v !== null) score = v;
          }
        }

        if (location_score === null) {
          const cardText = card.textContent || '';
          const locMatch =
            cardText.match(/Location\s*(\d+(?:\.\d)?)/i) ||
            cardText.match(/Location\s*score\s*(\d+(?:\.\d)?)/i);
          if (locMatch) {
            const v = parseFloat(locMatch[1]);
            if (!isNaN(v) && v >= 1 && v <= 10) location_score = v;
          }
        }

        // Only add if we found at least a name
        if (name) {
          console.log(
            '[DEBUG JS] NEW LOGIC Hotel pushed:',
            name,
            '| Stars:',
            stars,
            '| Price:',
            min_price,
            '| Score:',
            score
          );
          results.push({
            mode: 'Hotel',
            name,
            stars,
            score,
            location_score,
            min_price,
            max_price,
            currency,
            pageType: 'hotels',
          });
        }
      } catch (e) {
        console.error('Error parsing hotel card (new logic):', e);
      }
    });
  }

  // ==========================================
  // 4. EXPERIENCE CARDS (The activities page)
  // ==========================================
  const experienceCards = document.querySelectorAll('article');
  experienceCards.forEach((card) => {
    try {
      const nameEl = card.querySelector('h3');
      if (!nameEl) return;
      const priceGuard = card.querySelector('.text-base.font-bold');
      if (!priceGuard) return; // Skip non-experience articles (blog posts, widgets, etc.)
      let name = nameEl.textContent.trim();

      // Convert "8 hours", "1 day", or "90 minutes" text to duration in minutes
      let duration = null;
      const durationEl = card.querySelector('.text-sm.text-text-secondary');
      if (durationEl) {
        const text = durationEl.textContent.trim();
        let mins = 0;
        const hMatch = text.match(/(\d+)\s*hour/i);
        if (hMatch) mins += parseInt(hMatch[1], 10) * 60;
        const dMatch = text.match(/(\d+)\s*day/i);
        if (dMatch) mins += parseInt(dMatch[1], 10) * 1440;
        const mMatch = text.match(/(\d+)\s*min/i);
        if (mMatch) mins += parseInt(mMatch[1], 10);
        if (mins > 0) duration = mins;
      }

      // Grab the numerical rating (e.g., 4.6)
      let rating = null;
      const ratingEl = card.querySelector('.text-label-md.font-semibold');
      if (ratingEl) rating = parseFloat(ratingEl.textContent.trim());

      // Grab the final price (targets both regular and discounted prices)
      const priceEl = card.querySelector('.text-base.font-bold');
      let min_price = null;
      let max_price = null;
      if (priceEl) {
        const text = priceEl.textContent.trim();
        const numbers = text.match(/[\d,]+/g);
        if (numbers && numbers.length > 0) {
          const val = parseInt(numbers[0].replace(/,/g, ''), 10);
          if (!isNaN(val)) {
            min_price = val;
            max_price = val;
          }
        }
      }

      results.push({
        mode: 'Experience',
        name,
        duration,
        rating,
        min_price,
        max_price,
        pageType: 'experiences',
      });
    } catch (e) {
      console.error('Error parsing experience card:', e);
    }
  });

  // ==========================================
  // 5. TRIP DETAILS PAGE (The detailed itinerary)
  // ==========================================
  // This handles the page that shows after selecting a specific route
  try {
    const url = new URL(window.location.href);
    const isTripDetails = url.pathname.startsWith('/trips');
    if (isTripDetails) {
      const bodyText = document.body.innerText || '';

      // Build a mode string from the URL search parameter (captures selected airport/stop).
      let modeParts = [];
      const searchParam = url.searchParams.get('search');
      if (searchParam) {
        const decoded = decodeURIComponent(searchParam).replace(/\+/g, ' ');
        const parts = decoded
          .split(',')
          .map((p) => p.trim())
          .filter(Boolean);
        if (parts.length > 0) {
          let last = parts[parts.length - 1].replace(/-/g, ' ');
          last = last.replace(/\s+[A-Z]{3}\b/, '').trim();
          if (last) modeParts.push(last.toLowerCase());
        }
      }

      // Add transport types discovered on the page text.
      if (bodyText.includes('Fly')) modeParts.push('fly');
      if (bodyText.includes('Train')) modeParts.push('train');
      if (bodyText.includes('Bus')) modeParts.push('bus');
      if (bodyText.includes('Drive')) modeParts.push('drive');
      if (bodyText.includes('Ferry')) modeParts.push('ferry');

      const mode =
        modeParts.length > 0
          ? Array.from(new Set(modeParts)).join(', ')
          : 'multi-leg';

      // Extract duration from time elements first, then fallback to text regex.
      let duration = null;
      const timeEls = document.querySelectorAll('time[datetime]');
      const durations = [];
      timeEls.forEach((timeEl) => {
        const raw = timeEl.getAttribute('datetime') || '';
        if (raw.startsWith('PT')) {
          const hMatch = raw.match(/(\d+)H/);
          const mMatch = raw.match(/(\d+)M/);
          const hours = hMatch ? parseInt(hMatch[1], 10) : 0;
          const minutes = mMatch ? parseInt(mMatch[1], 10) : 0;
          const mins = hours * 60 + minutes;
          if (mins > 0) durations.push(mins);
        }
      });

      if (durations.length > 0) {
        duration = Math.max(...durations);
      } else {
        const durationMatches = [
          ...bodyText.matchAll(/(\d+)\s*h\s*(\d+)\s*m/gi),
        ];
        const textDurations = durationMatches.map(
          (m) => parseInt(m[1], 10) * 60 + parseInt(m[2], 10)
        );
        if (textDurations.length > 0) duration = Math.max(...textDurations);
      }

      // Extract price range if present (optional for matching).
      let min_price_total = null;
      let max_price_total = null;
      const priceMatches = [...bodyText.matchAll(/₹\s*([\d,]+)/g)];
      if (priceMatches.length > 0) {
        const values = priceMatches
          .map((m) => parseInt(m[1].replace(/,/g, ''), 10))
          .filter((v) => !isNaN(v));
        if (values.length > 0) {
          min_price_total = Math.min(...values);
          max_price_total = Math.max(...values);
        }
      }

      if (duration !== null || min_price_total !== null) {
        results.push({
          mode,
          duration,
          min_price: min_price_total,
          max_price: max_price_total,
          pageType: 'trip_details',
        });
      }
    }
  } catch (e) {
    console.error('[DEBUG JS] Error parsing trip details:', e);
  }

  console.log('[DEBUG JS] ============ SCRAPER END ============');
  console.log('[DEBUG JS] TOTAL RESULTS COLLECTED:', results.length);
  console.log('[DEBUG JS] Results data:', JSON.stringify(results, null, 2));
  return results;
};
