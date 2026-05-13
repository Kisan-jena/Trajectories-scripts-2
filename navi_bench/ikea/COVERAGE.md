# IKEA US Coverage Documentation
## URL Patterns, Query Parameters & Verifier Reference
**ikea.com/us/en/**
**Browser-Verified: May 2026**

---

## ⚡ Verification Methodology: **URL-BASED ONLY**

> [!IMPORTANT]
> **IKEA US is verified using URL-based matching exclusively.**
> No DOM inspection is required. Every user-facing filter state — keyword search,
> category path, color, price range, sort order — is **fully encoded in the URL**
> as query parameters. This makes URL comparison the authoritative, complete source
> of truth for verifying navigation accuracy.

| Aspect | Detail |
| :--- | :--- |
| **Verification type** | **URL-based** (no DOM, no cookies, no JS state) |
| **Why URL works** | All filters immediately update the address bar via `filters=` and `sort=` params |
| **Why DOM is NOT needed** | IKEA does not use client-side-only state; every filter click triggers a URL change |
| **Filter encoding** | Single `filters=` param with comma-separated `f-type:value` pairs |
| **Sort encoding** | Separate `sort=` param with uppercase constant values |
| **Login required?** | No — all pages are fully browsable without authentication |
| **Geo-blocking?** | No — US locale (`/us/en/`) is accessible globally |
| **AJAX filtering?** | No — each filter selection causes a full page navigation with URL update |

### Comparison with Other Domains

| Domain | Verification Method | Reason |
| :--- | :--- | :--- |
| **IKEA US** | URL only | All state in `q=`, `filters=`, `sort=` params |
| **Swappa** | URL only | All state in path + query params |
| **Mercari** | URL only | All state in `keyword=`, condition, price params |
| **Facebook Marketplace** | DOM + URL | Some state is client-side only |
| **Kayak** | DOM + URL | Flight results require DOM extraction |

---

## Overview

This document provides the authoritative reference for IKEA US URL structures, query parameter
encoding, and verifier matching logic. All patterns were validated through **3 dedicated browser
deep-dive sessions** against the live production site (May 2026), covering:

- Homepage → Search → Filter → Sort navigation flows
- Category page → Filter → Sort navigation flows
- Color filter ID mapping (all 13 colors verified individually)
- Sort parameter mapping (all 11 options verified)
- Price bucket encoding (verified across multiple categories)
- Multi-filter combination behavior

> **Site Profile:** IKEA US is a **furniture & home goods retailer** with a product-catalog
> architecture. Navigation uses both keyword search (`/us/en/search/?q=`) and hierarchical
> category browsing (`/us/en/cat/{slug}/`). The site offers 10,000+ products across
> furniture, storage, lighting, textiles, kitchenware, and home décor. No authentication
> is required to browse, search, or filter products.

> [!WARNING]
> **These URL patterns are NOT officially documented by IKEA.** They are reverse-engineered
> from browser observation across 3 deep-dive sessions. IKEA may change parameter names,
> values, or behavior without notice. All patterns documented here were browser-verified
> in May 2026.

> [!CAUTION]
> **Price bucket breakpoints are category-dependent.** The `f-price-buckets` values use
> internal cent-based codes (e.g., `PRICE_0_10000` = $0–$99.99) and the breakpoints
> change depending on the product category. Always verify bucket codes against the
> live site for the specific category being benchmarked.

---

## 1. Page Types

| Page Type | URL Pattern | Example |
| :--- | :--- | :--- |
| **Homepage** | `/us/en/` | `ikea.com/us/en/` |
| **Search Results** | `/us/en/search/?q={keyword}` | `/us/en/search/?q=desk` |
| **Category Listing** | `/us/en/cat/{slug}-{id}/` | `/us/en/cat/desks-20649/` |
| **Product Detail** | `/us/en/p/{product-slug}-{article}/` | `/us/en/p/micke-desk-white-s30213076/` |

### Detection Rules

| Rule | Pattern Match | Page Type |
| :--- | :--- | :--- |
| `/us/en/search/` in path | Keyword search results | Search |
| `/us/en/cat/` in path | Category listing page | Category |
| `/us/en/p/` in path | Individual product page | Product |
| `/us/en/` root only | Homepage | Landing |

> [!IMPORTANT]
> The verifier processes **search** and **category** pages. Individual product pages
> (`/us/en/p/`) are explicitly ignored. Search and category pages use **identical**
> filter and sort parameter formats.

---

## 2. URL Transition Flow

```
ikea.com/us/en/                              <- Homepage
    v type in search bar
ikea.com/us/en/search/?q=desk                <- Search results
    v apply color filter
ikea.com/us/en/search/?q=desk&filters=f-colors:10156
    v apply sort
ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH
```

```
ikea.com/us/en/                              <- Homepage
    v click Products > Desks
ikea.com/us/en/cat/desks-20649/              <- Category page
    v apply color filter
ikea.com/us/en/cat/desks-20649/?filters=f-colors:10005
    v apply sort
ikea.com/us/en/cat/desks-20649/?filters=f-colors:10005&sort=PRICE_LOW_TO_HIGH
```

### URL Anatomy

**Search with no filters:**
```
https://www.ikea.com/us/en/search/?q=bookshelf
```

**Search with all filters:**
```
https://www.ikea.com/us/en/search/?q=desk
  &filters=f-colors:10156,f-price-buckets:PRICE_0_10000
  &sort=PRICE_LOW_TO_HIGH
```

**Category with filters:**
```
https://www.ikea.com/us/en/cat/sofas-fu003/
  ?filters=f-colors:10003
  &sort=NEWEST
```

---

## 3. Query Parameters

| Filter | Parameter | Format | Example | Verifier Handling |
| :--- | :--- | :--- | :--- | :--- |
| **Search keyword** | `q` | Free text string | `q=desk` | Case-insensitive, whitespace-normalized |
| **Filters** | `filters` | `f-{type}:{value}` comma-separated | `filters=f-colors:10156` | Parsed into individual filter map |
| **Sort Order** | `sort` | Uppercase constant string | `sort=PRICE_LOW_TO_HIGH` | Alias-normalized exact match |

> [!IMPORTANT]
> **IKEA's filter architecture is unique.** Unlike Swappa/Mercari which use separate query
> params for each filter (`carrier=unlocked&condition=mint`), IKEA packs ALL filters into
> a **single `filters=` parameter** using comma-separated `f-type:value` pairs:
> ```
> filters=f-colors:10156,f-price-buckets:PRICE_0_10000
> ```
> The verifier must split this compound parameter and compare each filter individually.

> [!NOTE]
> **Filter parameter ordering does NOT matter.** `f-colors:10156,f-price-buckets:PRICE_0_10000`
> is equivalent to `f-price-buckets:PRICE_0_10000,f-colors:10156`. The verifier sorts
> filter values before comparison.

---

## 4. Color Filter (Browser-Verified)

### All Colors

| UI Label | `f-colors` ID | Notes |
| :--- | :--- | :--- |
| White | `10156` | |
| Black | `10005` | |
| Beige | `10003` | |
| Gray | `10008` | |
| Brown | `10017` | |
| Blue | `10006` | |
| Green | `10011` | |
| Turquoise | `10878` | |
| Yellow | `10015` | |
| Red | `10013` | |
| Pink | `10012` | |
| Orange | `10010` | |
| Multicolor | `10009` | |

### Color Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `grey` | `10008` (gray) |
| `cream`, `ivory`, `off-white` | `10003` (beige) |
| `tan`, `khaki` | `10003` (beige) |
| `teal`, `aqua`, `cyan` | `10878` (turquoise) |
| `purple`, `violet`, `lilac` | `10006` (blue) |
| `navy`, `dark blue` | `10006` (blue) |
| `gold` | `10015` (yellow) |
| `burgundy`, `maroon`, `wine` | `10013` (red) |
| `natural`, `wood` | `10017` (brown) |
| `silver`, `chrome`, `stainless` | `10008` (gray) |

---

## 5. Sort Options (Browser-Verified)

| UI Label | `sort` Value |
| :--- | :--- |
| Best match | *(default — no param)* |
| Price: low to high | `PRICE_LOW_TO_HIGH` |
| Price: high to low | `PRICE_HIGH_TO_LOW` |
| Newest | `NEWEST` |
| Customer rating | `CUSTOMER_RATING` |
| Name | `NAME_ASCENDING` |
| Most popular | `MOST_POPULAR` |
| Width | `WIDTH` |
| Height | `HEIGHT` |
| Depth | `DEPTH` |
| Length | `LENGTH` |

### Sort Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `cheapest`, `price_low`, `price low to high`, `price_asc` | `PRICE_LOW_TO_HIGH` |
| `most expensive`, `price_high`, `price high to low`, `price_desc` | `PRICE_HIGH_TO_LOW` |
| `newest first`, `most recent`, `new` | `NEWEST` |
| `rating`, `top rated`, `best rated`, `reviews` | `CUSTOMER_RATING` |
| `name`, `alphabetical`, `a-z`, `a to z` | `NAME_ASCENDING` |
| `popular`, `popularity`, `trending`, `best seller` | `MOST_POPULAR` |

---

## 6. Price Buckets (Browser-Verified)

Price bucket codes use **cents** internally. Breakpoints vary by category context.

### Search Price Buckets (e.g., "desk")

| UI Label | `f-price-buckets` Value |
| :--- | :--- |
| $0.00 - $99.99 | `PRICE_0_10000` |
| $100.00 - $199.99 | `PRICE_10000_20000` |
| $200.00 - $299.99 | `PRICE_20000_30000` |
| $300.00 - $399.99 | `PRICE_30000_40000` |
| $400.00+ | `PRICE_40000_MAX` |

### Category Price Buckets (e.g., "sofas")

| UI Label | `f-price-buckets` Value |
| :--- | :--- |
| $0.00 - $499.99 | `PRICE_0_50000` |
| $500.00 - $999.99 | `PRICE_50000_100000` |
| $1,000.00 - $1,499.99 | `PRICE_100000_150000` |
| $1,500.00 - $1,999.99 | `PRICE_150000_200000` |
| $2,000.00+ | `PRICE_200000_MAX` |

> [!WARNING]
> Price bucket breakpoints are **category-dependent** and set server-side. The verifier
> treats price bucket values as **opaque strings** — exact match only. The task generator
> uses only verified bucket codes from browser observation.

---

## 7. Category Slugs (Browser-Verified)

| Category | Slug | Full Path |
| :--- | :--- | :--- |
| Desks | `desks-20649` | `/us/en/cat/desks-20649/` |
| Sofas | `sofas-fu003` | `/us/en/cat/sofas-fu003/` |
| Beds | `beds-bm003` | `/us/en/cat/beds-bm003/` |
| Bookshelves | `bookcases-shelving-units-10382` | `/us/en/cat/bookcases-shelving-units-10382/` |
| Wardrobes | `wardrobes-19053` | `/us/en/cat/wardrobes-19053/` |
| Dining tables | `dining-tables-21825` | `/us/en/cat/dining-tables-21825/` |
| Chairs | `chairs-fu002` | `/us/en/cat/chairs-fu002/` |
| Dressers | `dressers-chests-of-drawers-20656` | `/us/en/cat/dressers-chests-of-drawers-20656/` |
| TV stands | `tv-media-furniture-10475` | `/us/en/cat/tv-media-furniture-10475/` |
| Mattresses | `mattresses-bm002` | `/us/en/cat/mattresses-bm002/` |

---

## 8. Additional Sidebar Filters (Category-Specific)

These filter types appear in the sidebar depending on the category context.
All use the same `filters=f-{type}:{value}` encoding pattern.

### Sidebar Layout (Browser-Verified — Search for "desk")

```
+-------------------------------+
| Sort ...................... v  |  <- Dropdown with radio buttons
| Size ...................... v  |  <- Width/Height/Depth/Length ranges
| Color ..................... v  |  <- Color swatches with item counts
| Type ...................... v  |  <- Category-specific subtypes
| Price ..................... v  |  <- Price range checkboxes
| Material .................. v  |  <- Material options
| Features .................. v  |  <- Special features
| Shape ..................... v  |  <- Product shapes
| Category .................. v  |  <- Sub-category refinement
| Series .................... v  |  <- IKEA product series names
| Finish .................... v  |  <- Surface finish types
+-------------------------------+
```

### Filter Encoding Table

| Filter Section | URL Key | Value Format | Example |
| :--- | :--- | :--- | :--- |
| **Size — Width** | `f-width` | Range code | `f-width:WIDTH_0_50` |
| **Size — Height** | `f-height` | Range code | `f-height:HEIGHT_0_50` |
| **Size — Depth** | `f-depth` | Range code | `f-depth:DEPTH_0_50` |
| **Size — Length** | `f-length` | Range code | `f-length:LENGTH_0_50` |
| **Type** | `f-types` | Numeric type ID | `f-types:38280` |
| **Material** | `f-materials` | Numeric material ID | `f-materials:16218` |
| **Features** | `f-features` | Numeric feature ID | `f-features:49874` |
| **Shape** | `f-shapes` | Numeric shape ID | `f-shapes:10646` |
| **Category** | `f-categories` | Numeric category ID | `f-categories:20649` |
| **Series** | `f-series` | Numeric series ID | `f-series:22534` |
| **Finish** | `f-finishes` | Numeric finish ID | `f-finishes:37465` |

### Filter Behavior (Browser-Verified)

- Selecting ANY filter **immediately** updates the URL and reloads results
- Active filters show as **pill badges** above the product grid (e.g., `white ×`)
- Clicking the `×` on a pill removes that filter and updates the URL
- Multiple filters can be stacked — combined with comma in `filters=` param
- Filter counts update dynamically (e.g., "White 359" → shows 359 white items)
- Color swatches are **multi-select** — clicking a second color adds it
- Sort is **single-select** — radio buttons, only one active at a time
- Price ranges are **checkboxes** — multiple can be selected

> [!NOTE]
> The verifier supports **all** `f-{type}:{value}` filters generically via the unified
> filter parser. However, benchmark tasks focus on the **universal** filters (Color,
> Price, Sort) that work identically across all search and category pages.

> [!WARNING]
> Category-specific filter IDs (Type, Material, Features, Shape, Series, Finish) are
> **numeric and opaque** — they cannot be guessed from the filter name. Each ID must be
> individually browser-verified for the specific category. These IDs may differ between
> categories (e.g., "Solid wood" material ID in Desks ≠ in Beds).

---

## 9. Domain Variations

| Domain | Accepted | Description |
| :--- | :---: | :--- |
| `www.ikea.com` | YES | Standard desktop |
| `ikea.com` | YES | Without www |
| `m.ikea.com` | YES | Mobile subdomain |
| `*.ikea.com` | YES | Any subdomain |
| `ikea.co.uk` | NO | UK site, different locale |
| `fakeikea.com` | NO | Not a subdomain |

> [!IMPORTANT]
> The verifier requires the `/us/en/` locale path prefix. URLs for other locales
> (e.g., `/gb/en/`, `/de/de/`) will not match.

---

## 10. Ignored Parameters

These parameters do not affect search semantics and are excluded from comparison:

### Tracking & Attribution (Ignored)
`utm_source`, `utm_medium`, `utm_campaign`, `gclid`, `fbclid`, `ref`, `itm_campaign`,
`itm_element`, `itm_content`, `itm_source`

### Pagination (Ignored)
`page` — page number for paginated results

### Session State (Ignored)
Any parameter not in the verified filter set is silently ignored during URL comparison.

---

## 11. Verifier Matching Rules

### Core Comparison Logic

| # | Field | Normalization | Comparison | Fail if GT has & Agent missing? |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Page type | search vs category | Must match GT page type | YES |
| 2 | Search keyword | Lowercase, whitespace-collapse | Case-insensitive match | YES (search only) |
| 3 | Category slug | Lowercase, strip trailing slash | Exact string match | YES (category only) |
| 4 | Colors | Name→ID alias resolution | Exact ID match | YES |
| 5 | Price bucket | Exact string | Exact string match | YES |
| 6 | Sort order | Alias resolution (see S5) | Exact string match | YES |
| 7 | Other filters | Exact f-type:value | Exact string match | YES |

### Precedence Rules (Hardened — No Auto-Pass Loopholes)

1. If ground truth specifies a field and agent **omits** it → **FAIL** (no auto-pass)
2. If ground truth **omits** a field → agent value is **ignored** (pass)
3. **No auto-pass loopholes**: every GT-specified field must be present and correct
4. First successful match across multi-GT URLs → **score = 1.0** (OR semantics)
5. All mismatches are logged with detailed diagnostic messages
6. Extra agent parameters not in GT are **ignored**
7. Tracking/session parameters (S10) are always ignored
8. Individual product pages (`/us/en/p/`) are ignored — never match

### Matching Flow

```
Agent URL -> Parse -> Normalize
  v
GT URL -> Parse -> Normalize
  v
Compare (sequential — first failure stops):
  1. page_type (search vs category)
  2. search_keyword (if search page)
  3. category_slug (if category page)
  4. filters (each f-type:value pair)
  5. sort
  v
All match? -> score = 1.0
Any mismatch? -> score = 0.0 (with mismatch field + details logged)
```

---

## 12. Search Behavior (Browser-Verified)

IKEA US uses a **standard search results page** (unlike Swappa's autocomplete-only):

```
+------------------------------------------------------------------+
|  [globe] US | English     [IKEA logo]     [search] desk     x Q  |
+------------------------------------------------------------------+
|  Products  Rooms  Deals  Design & ideas  Services                |
+------------------------------------------------------------------+
|  624 items for "desk"         Design your own desk [Get started] |
+------------------------------------------------------------------+
| Sort      v  |  Compare  |  Compare  |  Compare  |  Compare     |
| Size      v  |  [img]    |  [img]    |  [img]    |  [img]       |
| Color     v  |  MITTPLAN |  MITTPLAN |  UTMANING |  UTMANING    |
| Type      v  |  Desk,    |  Desk w/  |  Gaming   |  Gaming      |
| Price     v  |  white    |  add-on   |  desk,    |  desk,       |
| Material  v  |  $149.99  |  $249.99  |  black    |  black       |
| Features  v  |           |           |  $349.99  |  $309.99     |
| Shape     v  |           |           |           |              |
| Category  v  |           |           |           |              |
| Series    v  |           |           |           |              |
| Finish    v  |           |           |           |              |
+-------------+-------------------------------------------------- +
```

> [!IMPORTANT]
> IKEA US **does** have a `/search/?q=` URL pattern with full filter support.
> This is fundamentally different from Swappa (autocomplete-only, no search URL).

---

## 13. Listings Page Sidebar Layout (Browser-Verified Desktop)

```
Sort ...................... v   <- Dropdown: Best match, Price low/high, etc.
Size ...................... v   <- Width/Height/Depth/Length ranges
Color ..................... v   <- Color swatches with counts
Type ...................... v   <- Category-specific subtypes
Price ..................... v   <- Price range buckets with counts
Material .................. v   <- Material options
Features .................. v   <- Special features
Shape ..................... v   <- Product shapes
Category .................. v   <- Sub-category refinement
Series .................... v   <- IKEA product series
Finish .................... v   <- Surface finish types
```

### Filter Behavior

- Selecting a filter **immediately** updates the URL and reloads results
- Active filters show as **pill badges** above results (e.g., `white ×`)
- Multiple filters can be combined with comma separation
- Filter counts update dynamically
- Dropdowns are **multi-select** — multiple colors can be selected

---

## 14. Test & Benchmark Coverage

### Unit Tests

**90+ tests** across 16+ test classes, covering:

| Category | Tests | Focus |
| :--- | :---: | :--- |
| URL Parsing | 8 | Full parse pipeline, all filter types |
| Keyword Normalization | 5 | Case, whitespace, special chars |
| Category Slug Extraction | 5 | Slug parsing from path |
| Color Normalization | 13 | All colors, aliases |
| Sort Normalization | 11 | All sorts, aliases |
| Price Bucket Parsing | 5 | Bucket codes |
| Filter Combination | 6 | Multi-filter parsing |
| Domain Validation | 6 | Valid domains, rejections |
| Search Matching | 5 | Keyword + filters |
| Category Matching | 5 | Slug + filters |
| Color Matching | 4 | Match, mismatch, missing |
| Sort Matching | 3 | Match, mismatch, missing |
| Combination Matching | 5 | Multi-filter combos |
| Async Lifecycle | 5 | reset -> update -> compute |
| Multi-GT URLs | 3 | OR semantics |
| Edge Cases | 5 | Non-IKEA URLs, product pages, empty |

### Benchmark Dataset

**70 tasks** in `ikea_benchmark_tasks.csv` — **all hard difficulty**:

| Category | Count | Difficulty Strategy |
| :--- | :---: | :--- |
| Search Navigation | 10 | Navigate to correct search results |
| Category Navigation | 10 | Browse to specific category page |
| Color Filter | 10 | Search/category + color filter |
| Sort Selection | 10 | Search/category + sort order |
| Red Herring | 10 | Narrative distractors |
| Multi-Filter | 10 | 3+ simultaneous filters |
| Ultra-Hard | 10 | Budget arithmetic + narrative + multi-filter |

---

## Appendix A: Live URL Examples

### Search (no filters)
```
https://www.ikea.com/us/en/search/?q=desk
```

### Search with color filter
```
https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156
```
^ White desks

### Search with sort
```
https://www.ikea.com/us/en/search/?q=bookshelf&sort=PRICE_LOW_TO_HIGH
```

### Search with multiple filters
```
https://www.ikea.com/us/en/search/?q=sofa&filters=f-colors:10003,f-price-buckets:PRICE_0_50000&sort=NEWEST
```
^ Beige sofas under $500, newest first

### Category page (no filters)
```
https://www.ikea.com/us/en/cat/desks-20649/
```

### Category with filters
```
https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10008&sort=PRICE_LOW_TO_HIGH
```
^ Gray sofas, cheapest first

### Product page (ignored by verifier)
```
https://www.ikea.com/us/en/p/micke-desk-white-s30213076/
```

---

## Appendix B: Comparison with Other Domains

| Feature | IKEA US | Swappa | Mercari |
| :--- | :--- | :--- | :--- |
| **Type** | E-commerce (furniture/home) | E-commerce (used tech) | E-commerce (secondhand) |
| **URL model** | Path + query params | Path-based catalog | Query-param search |
| **Primary nav** | Search + category browse | Browse by product | Keyword search |
| **Search path** | `/us/en/search/?q=` | `/buy/{slug}` | `/search/?keyword=` |
| **Filter encoding** | `filters=f-type:value` | Query params | Query params |
| **Price encoding** | Bucket codes (cents) | Not in URL | Cents |
| **Color filter** | Numeric IDs | String slugs | N/A |
| **Sort values** | UPPERCASE constants | String slugs | Numeric IDs |
| **Multi-select** | Yes (comma-separated) | No (single-select) | Yes (hyphen-separated) |
| **Login required** | No | No | No |
| **Pagination** | Yes (page param) | Yes (page-based) | No (infinite scroll) |

---
