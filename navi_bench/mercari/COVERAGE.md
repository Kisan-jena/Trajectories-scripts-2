# Mercari Coverage Documentation
## URL Patterns, Query Parameters & Verifier Reference
**mercari.com**
**Browser-Verified: April 2026**

---

## Overview

This document provides the authoritative reference for Mercari's URL structures, query parameter
encoding, and verifier matching logic. All patterns were validated through dedicated browser
deep-dive sessions against the live production site (April 2026).

> **Important:** Mercari is a modern JavaScript SPA (React-based). All search filters are encoded
> as URL query parameters on the `/search/` path. No authentication is required to browse, search,
> or filter — the site is fully accessible without login.

> [!WARNING]
> **Prices are encoded in CENTS, not dollars!** $25.00 = `minPrice=2500`. This is a critical
> encoding detail confirmed via browser observation. All price comparisons in the verifier use
> raw cent values from the URL.

> [!CAUTION]
> **These URL patterns are NOT officially documented by Mercari.** They are reverse-engineered
> from browser observation and dedicated deep-dive sessions. Mercari may change parameter names,
> values, or behavior without notice. All patterns documented here were browser-verified
> in April 2026 but may drift over time.

---

## 1. Page Types

| Page Type | URL Pattern | Example |
| :--- | :--- | :--- |
| **Homepage** | `/` | `mercari.com/` |
| **Search Results** | `/search/?keyword=...` | `/search/?keyword=shoes` |
| **Category Browse** | `/us/category/{name}-{id}/` | `/us/category/electronics-7/` |
| **Item Listing** | `/us/item/m{numeric_id}/` | `/us/item/m72277772433/` |

### Detection Rules

| Rule | Pattern Match | Page Type |
| :--- | :--- | :--- |
| `/search/` in path | Search results page | Search |
| `/us/category/` in path | Category browse page | Category |
| `/us/item/m` in path | Individual product listing | Listing |
| `/` root only | Homepage | Landing |

> [!IMPORTANT]
> The verifier only processes **search** and **category** URLs. Item listing pages
> (`/us/item/m{id}/`) are explicitly ignored and will not produce a match.

---

## 1b. Homepage & Navigation Layout (Browser-Verified Apr 2026)

```
┌──────────────────────────────────────────────────────────────────┐
│  mercari                                          🔍 Search     │
├──────────────────────────────────────────────────────────────────┤
│  [Women] [Men] [Electronics] [Toys] [Gaming] [Handbags] [Home]  │
│  [Vintage] [Beauty] [Kids] [Sports] [Handmade] [Office] [Pet]   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Featured                                                        │
│  ┌──────┬──────┬──────┬──────┬──────┐                           │
│  │ IMG  │ IMG  │ IMG  │ IMG  │ IMG  │                           │
│  │$25.00│$42.00│$18.00│$99.00│$55.00│                           │
│  │Shoes │Watch │Bag   │Phone │Dress │                           │
│  └──────┴──────┴──────┴──────┴──────┘                           │
│                                                                  │
│  Just for you                                                    │
│  ┌──────┬──────┬──────┬──────┬──────┐                           │
│  │ IMG  │ IMG  │ IMG  │ IMG  │ IMG  │                           │
│  │ SOLD │$12.00│$35.00│$8.00 │$150  │                           │
│  └──────┴──────┴──────┴──────┴──────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

Key observations:
- Top navigation bar lists all 15 product categories as clickable links
- Each category link navigates to `/us/category/{name}-{id}/`
- No login required — homepage is fully browsable
- No location-based filtering (unlike Facebook Marketplace)
- SOLD items show a "SOLD" overlay badge on the image

---

## 2. Search URLs & Query Parameters

### URL Anatomy

**Basic search:**
```
https://www.mercari.com/search/?keyword=nike+shoes&minPrice=5000&maxPrice=15000
```

**Full search with all filters:**
```
https://www.mercari.com/search/
  ?keyword=nike+shoes
  &minPrice=5000
  &maxPrice=15000
  &sortBy=3
  &itemConditions=1-2
  &categoryIds=77
  &brandIds=4578
  &shippingPayerIds=2
  &countrySources=1
  &withDealsOnly=true
  &statusIds=1
  &colorIds=1
```

### Query Parameters

| Filter | Parameter | Values / Format | Verifier Handling |
| :--- | :--- | :--- | :--- |
| **Search Query** | `keyword` | URL-encoded string | Case-insensitive, whitespace-normalized |
| **Min Price** | `minPrice` | Integer (in **cents**) | Exact integer match |
| **Max Price** | `maxPrice` | Integer (in **cents**) | Exact integer match |
| **Sort Order** | `sortBy` | `1`=best match, `2`=newest, `3`=price low→high, `4`=price high→low | Alias-normalized exact match |
| **Item Condition** | `itemConditions` | `1`–`5` (see §3) | Multi-select, sorted-set comparison |
| **Category** | `categoryIds` | Numeric ID | Exact match |
| **Brand** | `brandIds` | Numeric ID | Exact match |
| **Free Shipping** | `shippingPayerIds` | `2` = Free Shipping | Alias-normalized exact match |
| **Item Origin** | `countrySources` | `1`=USA, `2`=Japan | Alias-normalized exact match |
| **Deals Only** | `withDealsOnly` | `true` | Exact boolean match |
| **Status** | `statusIds` | `1`=On sale, `2`=Sold out | Alias-normalized exact match |
| **Color** | `colorIds` | Numeric ID (e.g., `1`=Black) | Exact match |

---

## 3. Sort Options (Browser-Verified)

| UI Label | `sortBy` Value | Normalized Key |
| :--- | :--- | :--- |
| Sort by best match | `1` | `1` |
| Sort by newest first | `2` | `2` |
| Sort by lowest price first | `3` | `3` |
| Sort by highest price first | `4` | `4` |

The verifier also accepts these aliases from agent URLs:

| Alias | Normalized To |
| :--- | :--- |
| `best_match`, `bestmatch`, `default`, `relevance` | `1` |
| `newest`, `newest_first`, `date_listed`, `recently_listed` | `2` |
| `price_asc`, `price_low`, `lowest_price`, `price_low_to_high` | `3` |
| `price_desc`, `price_high`, `highest_price`, `price_high_to_low` | `4` |

---

## 4. Item Conditions (Browser-Verified)

| UI Label | `itemConditions` Value |
| :--- | :--- |
| New | `1` |
| Like new | `2` |
| Good | `3` |
| Fair | `4` |
| Poor | `5` |

### Multi-Select Encoding

Mercari uses a **hyphen separator** for multi-select conditions:

```
itemConditions=1-2     ← New AND Like new
itemConditions=1-2-3   ← New AND Like new AND Good
itemConditions=3-4-5   ← Good AND Fair AND Poor
```

The verifier normalizes multi-select conditions to a **sorted list** and compares
order-independently. Both `1-2` and `2-1` resolve to `["1", "2"]`.

### Alias Resolution

The verifier also accepts string aliases:

| Alias | Normalized To |
| :--- | :--- |
| `new` | `1` |
| `like_new`, `like new`, `likenew` | `2` |
| `good` | `3` |
| `fair` | `4` |
| `poor` | `5` |

---

## 5. Price Encoding (Browser-Verified)

> [!CAUTION]
> **ALL prices are in CENTS!** This is the single most important encoding detail for Mercari.
> $1.00 = `100` in the URL. Getting this wrong will cause every price-related task to fail.

### Price Preset Mapping (Sidebar Radio Buttons)

| UI Label | URL Parameters |
| :--- | :--- |
| Under $25 | `maxPrice=2500` |
| $25 to $50 | `minPrice=2500&maxPrice=5000` |
| $50 to $100 | `minPrice=5000&maxPrice=10000` |
| $100 to $200 | `minPrice=10000&maxPrice=20000` |
| $200 and up | `minPrice=20000` |

### Custom Price Range

The sidebar also has a custom range input: `[$ Min] — [$ Max] [Apply]`

The user enters dollar amounts (e.g., $75, $150) and Mercari converts them to cents
in the URL:
```
$75 min, $150 max → minPrice=7500&maxPrice=15000
```

### Verifier Behavior

- Price fields are compared as **exact integers** (in cents)
- If GT specifies `minPrice` and agent omits it → **FAIL**
- If GT omits `minPrice`, agent's value is **ignored** (pass)
- Both `minPrice` and `maxPrice` are independently validated

---

## 6. Category System (Browser-Verified)

### Top Navigation Bar Categories

| Category | Nav Bar Label | Category URL | Category ID |
| :--- | :--- | :--- | :--- |
| Women | Women | `/us/category/women-1/` | `1` |
| Men | Men | `/us/category/men-2/` | `2` |
| Electronics | Electronics | `/us/category/electronics-7/` | `7` |
| Toys | Toys | `/us/category/toys-*` | TBD |
| Gaming | Gaming | `/us/category/gaming-*` | TBD |
| Handbags | Handbags | `/us/category/handbags-*` | TBD |
| Home | Home | `/us/category/home-*` | TBD |
| Vintage | Vintage | `/us/category/vintage-*` | TBD |
| Beauty | Beauty | `/us/category/beauty-*` | TBD |
| Kids | Kids | `/us/category/kids-*` | TBD |
| Sports | Sports | `/us/category/sports-*` | TBD |
| Handmade | Handmade | `/us/category/handmade-*` | TBD |
| Office | Office | `/us/category/office-*` | TBD |
| Pet | Pet | `/us/category/pet-*` | TBD |
| Outdoor | Outdoor | `/us/category/outdoor-*` | TBD |

### Dual Category Encoding

Categories can appear in **two places** in a Mercari URL:

1. **URL Path:** `/us/category/electronics-7/` → category ID `7`
2. **Query Parameter:** `categoryIds=7`

The verifier checks **both** locations. If the GT has a category ID from either source,
the agent must provide a matching ID from either source.

### Category Path Extraction

The verifier extracts category IDs from paths using this pattern:
```
/us/category/{name}-{id}/  →  extract {id}
```

Example: `/us/category/electronics-7/` → `"7"`

> [!NOTE]
> Category IDs from the path and from `categoryIds` query param are treated
> equivalently by the verifier. The agent can use either representation.

---

## 7. Brand Filter (Browser-Verified)

Brands are represented as **numeric IDs** in the URL:

```
brandIds=4578   ← Nike
```

### Browser-Verified Brand IDs

| Brand | `brandIds` Value |
| :--- | :--- |
| Nike | `4578` |

> [!WARNING]
> Brand IDs are **unstable** — Mercari may reassign numeric IDs over time.
> The verifier compares brand IDs as **exact strings**, not by brand name.
> Benchmark tasks that use brand filters should have their IDs verified
> at creation time and documented here.

### Sidebar Brand Filter

The left sidebar shows a searchable brand checklist:
```
Brand ................. ▲
  🔍 Search
  ☐ Nike
  ☐ Adidas
  ☐ Air Jordan
  ☐ VANS
  ☐ Crocs
  ☐ UGG Australia
  ☐ Converse
  ☐ New Balance
  (... more)
```

Selecting a brand checkbox updates the URL with `brandIds={numeric_id}`.

---

## 8. Shipping & Origin Filters (Browser-Verified)

### Free Shipping

| Filter State | URL Parameter |
| :--- | :--- |
| No filter (any shipping) | *(parameter absent)* |
| Free Shipping only | `shippingPayerIds=2` |

The verifier accepts aliases: `free`, `free_shipping`, `seller` → `"2"`

### Item Origin

| UI Label | `countrySources` Value |
| :--- | :--- |
| Any | *(parameter absent)* |
| USA | `1` |
| Japan | `2` |

The verifier accepts aliases: `usa`, `us`, `united_states` → `"1"`, `japan`, `jp` → `"2"`

### Sidebar Layout

```
Free Shipping ......... ▼
  ☐ Free Shipping

Item origin ........... ▼
  ● Any
  ○ USA
  ○ Japan
```

---

## 9. Deals Filter (Browser-Verified)

| Filter State | URL Parameter |
| :--- | :--- |
| No filter | *(parameter absent)* |
| Deals only | `withDealsOnly=true` |

Deals items show a discount percentage badge on the listing card (e.g., "10%", "42%").

---

## 10. Status Filter (Browser-Verified)

| UI Label | `statusIds` Value |
| :--- | :--- |
| On sale (active) | `1` |
| Sold out | `2` |

The verifier accepts aliases: `on_sale`, `active` → `"1"`, `sold_out`, `sold` → `"2"`

> [!NOTE]
> The status filter is primarily available in the **mobile filter drawer**.
> On desktop, it may not be visible in the sidebar. The verifier supports
> it regardless of UI visibility.

---

## 11. Color Filter

| Color | `colorIds` Value |
| :--- | :--- |
| Black | `1` |

> [!NOTE]
> Only `Black = 1` has been browser-verified. Additional color mappings will
> be added as they are confirmed. The verifier does exact string match on
> `colorIds` values.

---

## 12. Domain Variations

The verifier accepts **all** valid Mercari domains:

| Domain | Accepted | Description |
| :--- | :---: | :--- |
| `mercari.com` | ✅ | Primary (no www) |
| `www.mercari.com` | ✅ | Standard desktop |
| `m.mercari.com` | ✅ | Mobile web (if exists) |
| `*.mercari.com` | ✅ | Any subdomain |
| `fakemercari.com` | ❌ | Not a subdomain |
| `mercari.co.jp` | ❌ | Different TLD (Japanese site) |
| `google.com` | ❌ | Not Mercari |

### Domain Validation Rules

1. **Exact match** against known domains: `mercari.com`, `www.mercari.com`
2. **Subdomain match**: any domain ending in `.mercari.com`
3. **Rejection**: domains that don't match the above rules

> [!NOTE]
> Mercari Japan (`mercari.com/jp/`) is a different marketplace with different
> URL patterns and product listings. The verifier only handles the US site
> (`mercari.com` without country-specific TLD).

---

## 13. Ignored Parameters

These parameters encode session state, UI preferences, or tracking data.
They do **not** affect search semantics and are excluded from comparison:

### Tracking & Attribution (Ignored)
`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`,
`gclid`, `msclkid`, `fbclid`, `ref`, `source`

### Session State (Ignored)
Any parameter not in the verified filter set is silently ignored during
URL comparison. Extra parameters in the agent URL do not cause a mismatch.

---

## 14. Verifier Matching Rules

### Core Comparison Logic

| # | Field | Normalization | Comparison | Fail if GT has & Agent missing? |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Search keyword | URL-decode, lowercase, collapse whitespace | Case-insensitive string match | ✅ Yes |
| 2 | Min price | Parse as integer (cents) | Exact integer match | ✅ Yes |
| 3 | Max price | Parse as integer (cents) | Exact integer match | ✅ Yes |
| 4 | Sort order | Alias resolution (see §3) | Exact string match | ✅ Yes |
| 5 | Item conditions | Split on hyphen, normalize each, sort | Sorted list equality | ✅ Yes |
| 6 | Category ID | From `categoryIds` param OR path segment | Exact string match | ✅ Yes |
| 7 | Brand ID | From `brandIds` param | Exact string match | ✅ Yes |
| 8 | Shipping payer | Alias resolution (see §8) | Exact string match | ✅ Yes |
| 9 | Country source | Alias resolution (see §8) | Exact string match | ✅ Yes |
| 10 | Deals only | Lowercase, strip | Exact string match | ✅ Yes |
| 11 | Status ID | Alias resolution (see §10) | Exact string match | ✅ Yes |
| 12 | Color ID | Raw value | Exact string match | ✅ Yes |

### Precedence Rules (Hardened — No Auto-Pass Loopholes)

1. If ground truth specifies a field and agent **omits** it → **FAIL** (no auto-pass)
2. If ground truth **omits** a field → agent value is **ignored** (pass)
3. **No auto-pass loopholes**: every GT-specified field must be present and correct
4. Keyword matching is **case-insensitive** and **whitespace-normalized**
5. Conditions are compared as **sorted sets** — order does not matter
6. Price values are compared as **raw integers** (cents) — no dollar conversion
7. First successful match across multi-GT URLs → **score = 1.0** (OR semantics)
8. All mismatches are logged with detailed diagnostic messages
9. Extra agent parameters not in GT are **ignored** (agent can have more filters)
10. Tracking/session parameters (§13) are always ignored
11. Category can match via **path segment** OR **query param** — either is valid

### Matching Flow

```
Agent URL → Parse → Normalize
  ↓
GT URL → Parse → Normalize
  ↓
Compare (sequential — first failure stops):
  1. keyword
  2. min_price (cents)
  3. max_price (cents)
  4. sort_by
  5. item_conditions (sorted set)
  6. category_ids (param OR path)
  7. brand_ids
  8. shipping_payer_ids
  9. country_sources
  10. with_deals_only
  11. status_ids
  12. color_ids
  ↓
All match? → score = 1.0
Any mismatch? → score = 0.0 (with mismatch field + details logged)
```

---

## 15. Listing Card Anatomy (Browser-Verified)

### Standard Listing Card

```
┌──────────────────────┐
│   [DISCOUNT BADGE]   │  ← "10%", "42%", "74%" with icon
│                      │
│   [LISTING IMAGE]    │
│                      │
├──────────────────────┤
│  Men's Nike Shoes    │  ← Title
│  $252.00  $280.00    │  ← Current price + strikethrough original
│                      │
└──────────────────────┘
```

### Sold Listing Card

```
┌──────────────────────┐
│   ┌──────────────┐   │
│   │     SOLD     │   │  ← Red "SOLD" overlay badge
│   └──────────────┘   │
│   [LISTING IMAGE]    │
│                      │
├──────────────────────┤
│  Vintage Watch       │  ← Title
│  $45.00              │  ← Price (no discount)
│                      │
└──────────────────────┘
```

### Key Observations

- **SOLD** items show a prominent "SOLD" badge overlay on the image
- **Discount percentage** badges appear on items with price drops
- **No location info** on listing cards (unlike Facebook Marketplace)
- Prices on cards are displayed in **dollars**, but URL parameters use **cents**
- **No pagination** — Mercari uses infinite scroll to load more results
- Clicking a listing navigates to `/us/item/m{id}/` — a page the verifier ignores

> [!IMPORTANT]
> The verifier does NOT validate listing-level information (title, displayed price,
> sold status). It only compares URL-level search parameters. Listing card details
> are documented here for agent developers who may need to interact with results.

---

## 16. Sidebar Filter Layout (Browser-Verified Desktop)

```
Filter by
─────────────────
Size .................. ▼  (context-dependent, e.g., shoes)
Price ................. ▲
  ● Any
  ○ Under $25
  ○ $25 to $50
  ○ $50 to $100
  ○ $100 to $200
  ○ $200 and up
  [$ Min] — [$ Max]  [Apply]
Deals ................. ▼
Free Shipping ......... ▼
Brand ................. ▲
  🔍 Search
  ☐ Nike
  ☐ Adidas
  ☐ Air Jordan
  ☐ VANS
  ☐ Crocs
  ☐ UGG Australia
  ☐ Converse
  ☐ New Balance
  (... more)
Category .............. ▲
  All
    Men
      Shoes
        Athletic
        Fashion Sneakers
        Boots
        Oxfords
        (Show more)
    Women
    Kids
    Toys & Collectibles
    (Show more)
Condition ............. ▲
  ☐ New
  ☐ Like new
  ☐ Good
  ☐ Fair
  ☐ Poor
Item origin ........... ▼
  ● Any
  ○ USA
  ○ Japan
Status ................ ▼  (mobile filter drawer only)
```

---

## 17. Search Results Page Anatomy (Browser-Verified)

The Mercari search results page uses a two-column layout on desktop:

```
┌──────────────────────────────────────────────────────────────────┐
│  mercari                                 🔍 [Search bar]        │
├──────────────────────────────────────────────────────────────────┤
│  [Women] [Men] [Electronics] ... [Outdoor]    [Sell] [Login]    │
├────────────┬─────────────────────────────────────────────────────┤
│            │  "nike shoes" — 10,000+ results                    │
│  Filter by │  Sort by: [Best Match ▼]                           │
│  ─────── │                                                     │
│  Price   ▲ │  ┌──────┬──────┬──────┬──────┬──────┐             │
│  ● Any     │  │ IMG  │ IMG  │ IMG  │ IMG  │ IMG  │             │
│  ○ Under.. │  │$50.00│$75.00│$42.00│$88.00│$120  │             │
│  [$Min][$M]│  │Nike..│Nike..│Nike..│Nike..│Nike..│             │
│  Deals   ▼ │  └──────┴──────┴──────┴──────┴──────┘             │
│  Free Sh ▼ │  ┌──────┬──────┬──────┬──────┬──────┐             │
│  Brand   ▲ │  │ IMG  │ IMG  │10%   │ SOLD │ IMG  │             │
│  ☐ Nike    │  │$35.00│$99.00│$60.00│$25.00│$45.00│             │
│  ☐ Adidas  │  │Nike..│Nike..│Nike..│Nike..│Nike..│             │
│  Category▲ │  └──────┴──────┴──────┴──────┴──────┘             │
│  Condtn  ▲ │                                                     │
│  Origin  ▼ │  (infinite scroll — more results load on scroll)   │
├────────────┴─────────────────────────────────────────────────────┤
│  Footer — About · Blog · Careers · Sustainability              │
└──────────────────────────────────────────────────────────────────┘
```

Key observations:
- **Two-column layout**: filters on the left, results grid on the right
- **Sort dropdown** appears above results (Best Match, Newest, Price Low, Price High)
- **Result count** displayed prominently ("10,000+ results")
- **Infinite scroll** — no pagination buttons, results load as user scrolls down
- Results display as a **5-column grid** on desktop (fewer columns on mobile)
- **Filter sidebar** is scrollable and stays fixed while results scroll
- Selecting any filter **immediately** updates the URL and results (no "Apply" button except for custom price range)

---

## 18. Test & Benchmark Coverage

### Unit Tests

**100+ tests** across 15 test classes, covering:

| Category | Tests | Focus |
| :--- | :---: | :--- |
| URL Parsing | 8 | Full parse pipeline, all filter types |
| Query Normalization | 6 | Case, whitespace, URL-decode |
| Price Range (Cents) | 8 | Min/max in cents, preset ranges, mismatch |
| Condition Matching | 8 | All 5 conditions, multi-select, aliases |
| Sort Matching | 6 | All 4 sort values, aliases, mismatch |
| Category Matching | 6 | Category ID match/mismatch, path extraction |
| Brand Matching | 6 | Brand ID match, numeric IDs |
| Shipping & Origin | 6 | Free shipping, country source |
| Deals & Status | 4 | Deals-only, status filters |
| Full URL Match Integration | 12 | All mismatch + combination scenarios |
| Domain Validation | 6 | Valid domains, rejections |
| Async Lifecycle | 5 | `reset` → `update` → `compute` |
| Multi-GT URLs | 3 | OR semantics |
| Edge Cases | 6 | Non-Mercari URLs, item pages, empty URLs |
| Normalization Helpers | 6 | Sort, condition, query normalizer functions |

### Benchmark Dataset

**70 tasks** in `mercari_benchmark_tasks.csv` — **all hard difficulty**:

| Category | Count | Difficulty Strategy |
| :--- | :---: | :--- |
| Price Math (cents conversion) | 12 | Budget/price descriptions in dollars → cents in URL |
| Multi-Condition Search | 10 | "Like new or new condition" → `itemConditions=1-2` |
| Brand + Category Combos | 10 | "Nike shoes under $100" → brandIds + categoryIds + maxPrice |
| Red Herring Tasks | 10 | Irrelevant details, personal anecdotes mixed in |
| Sort + Filter Combos | 10 | "Cheapest new electronics" → sortBy + itemConditions + categoryIds |
| Free Shipping + Origin | 8 | "Japanese items with free shipping" → origin + shipping |
| Ultra-Hard Combos | 10 | 5+ simultaneous filters, budget arithmetic, cents math |

---

## Appendix A: Live URL Examples

### Basic Search (shoes, any filter)
```
https://www.mercari.com/search/?keyword=shoes
```

### Search with Price Range (in cents)
```
https://www.mercari.com/search/?keyword=iphone+15&minPrice=20000&maxPrice=50000
```
↑ $200–$500 range (200×100 = 20000, 500×100 = 50000)

### Search with Condition + Sort
```
https://www.mercari.com/search/?keyword=nike+shoes&itemConditions=1&sortBy=3
```
↑ New condition only, sorted by lowest price first

### Multi-Condition Search
```
https://www.mercari.com/search/?keyword=bag&itemConditions=1-2
```
↑ New AND Like new conditions

### Category Browse
```
https://www.mercari.com/us/category/electronics-7/
```
↑ Electronics category (ID=7)

### Full Filter Combination
```
https://www.mercari.com/search/
  ?keyword=nike+shoes
  &minPrice=5000
  &maxPrice=15000
  &itemConditions=1
  &sortBy=3
  &shippingPayerIds=2
  &countrySources=1
```
↑ Nike shoes, $50–$150, New only, lowest price first, free shipping, USA origin

### Item Listing Page
```
https://www.mercari.com/us/item/m72277772433/
```
↑ Individual listing — **ignored by the verifier**

---

## Appendix B: Comparison with Other Domains

| Feature | Mercari | Facebook Marketplace | Trainline | Expedia |
| :--- | :--- | :--- | :--- | :--- |
| **Type** | E-commerce (secondhand) | E-commerce (local) | Travel (trains) | Travel (hotels/flights) |
| **Filter encoding** | Query params | Query params | Query params | Compound `leg` params |
| **Price encoding** | **Cents** ($25 = 2500) | Dollars ($25 = 25) | N/A | N/A |
| **Search path** | `/search/?keyword=` | `/marketplace/{city}/search/?query=` | `/book/results?...` | `/Hotel-Search?...` |
| **Conditions** | Numeric IDs (`1`–`5`) | String keys (`new`, `used_good`) | N/A | N/A |
| **Multi-condition** | Hyphen separator (`1-2`) | Not supported | N/A | N/A |
| **Sort values** | Numeric IDs (`1`–`4`) | String keys (`price_ascend`) | N/A | N/A |
| **Location** | Not in URL | City slug in path | Station URN codes | Airport IATA codes |
| **Categories** | Numeric IDs (path or param) | String slugs in path | N/A (single domain) | N/A (hotel/flight) |
| **Brands** | Numeric IDs | Numeric make IDs | N/A | N/A |
| **Date handling** | N/A | `daysSinceListed` (recency) | ISO datetime | ISO date |
| **Passengers/count** | N/A | N/A | DOB-based encoding | Room/traveler counts |
| **Login required** | No | Partial (modal overlay) | No | No |
| **Deals filter** | Yes (`withDealsOnly=true`) | No | N/A | N/A |
| **Item origin** | Yes (`countrySources`) | No | N/A | N/A |

---
