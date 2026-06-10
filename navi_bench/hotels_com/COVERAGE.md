# Hotels.com Coverage Documentation
## URL Patterns, Query Parameters & Verifier Reference
**hotels.com**
**Browser-Verified: June 2026**

---

## Overview

This document provides the authoritative reference for Hotels.com's URL structures, query parameter
encoding, and verifier matching logic. All patterns were validated through browser sessions against
the live production site (June 2026).

> **Important:** Hotels.com is part of the **Expedia Group** and shares the same URL structure as
> Expedia for hotel searches (`/Hotel-Search` path with identical query parameters). This is a
> **URL-BASED** verifier — all search state is encoded in URL query parameters, no DOM parsing needed.

> [!NOTE]
> Hotels.com uses prices in **DOLLARS** (not cents, unlike Mercari). $200 = `f-price-max=200`.

> [!CAUTION]
> These URL patterns are **NOT officially documented** by Hotels.com. They are reverse-engineered
> from browser observation. Hotels.com may change parameter names, values, or behavior without
> notice. All patterns documented here were browser-verified in June 2026.

---

## 1. Page Types

| Page Type | URL Pattern | Example |
| :--- | :--- | :--- |
| **Homepage** | `/` | `hotels.com/` |
| **Hotel Search Results** | `/Hotel-Search?destination=...` | `/Hotel-Search?destination=New%20York` |
| **Property Details** | `/ho{numeric_id}/` | `/ho123456/` |

### Detection Rules

| Rule | Pattern Match | Page Type |
| :--- | :--- | :--- |
| `/Hotel-Search` in path | Hotel search results | Search |
| `/ho{id}/` in path | Individual property page | Property |
| `/` root only | Homepage | Landing |

> [!IMPORTANT]
> The verifier only processes **Hotel-Search** URLs. Property detail pages
> (`/ho{id}/`) are explicitly ignored and will not produce a match.

---

## 2. URL-Based vs DOM-Based

Hotels.com is a **URL-BASED** verification target:

| Aspect | Status |
| :--- | :--- |
| Search parameters in URL | ✅ All encoded as query params |
| Filters in URL | ✅ `f-star-rating`, `f-price-min`, `f-amenities`, etc. |
| Sort in URL | ✅ `sort=PRICE_LOW_TO_HIGH` |
| Login required | ❌ No — fully browsable without login |
| JavaScript-only state | ❌ No — URL reflects complete search state |
| DOM scraping needed | ❌ No — URL alone is sufficient |

**Conclusion:** URL-based verification is appropriate. The URL contains the complete search
specification. No DOM parsing or JavaScript execution is needed.

---

## 3. Search URLs & Query Parameters

### URL Anatomy

**Basic search:**
```
https://www.hotels.com/Hotel-Search?destination=New%20York&startDate=2026-07-01&endDate=2026-07-05&rooms=1&adults=2
```

**Full search with all filters:**
```
https://www.hotels.com/Hotel-Search
  ?destination=New%20York%2C%20New%20York%2C%20United%20States%20of%20America
  &regionId=2621
  &startDate=2026-07-01
  &endDate=2026-07-05
  &adults=2
  &rooms=1
  &sort=PRICE_LOW_TO_HIGH
  &f-star-rating=4,5
  &f-price-min=100
  &f-price-max=300
  &f-amenities=WIFI,POOL
  &f-guest-rating=8
  &paymentType=FREE_CANCELLATION
  &children=1_5,1_10
```

### Query Parameters

| Filter | Parameter | Values / Format | Verifier Handling |
| :--- | :--- | :--- | :--- |
| **Destination** | `destination` | URL-encoded string | Case-insensitive, city-part only |
| **Region ID** | `regionId` | Numeric ID (e.g., `2621`) | Exact match (if GT specifies) |
| **Check-in** | `startDate` | `YYYY-MM-DD` | Date-normalized exact match |
| **Check-out** | `endDate` | `YYYY-MM-DD` | Date-normalized exact match |
| **Adults** | `adults` | Integer or comma-separated (multi-room) | Summed for multi-room |
| **Rooms** | `rooms` | Integer | Exact match |
| **Children** | `children` | `RoomIdx_Age` format (e.g., `1_5,1_10`) | Count + sorted ages |
| **Sort** | `sort` | See §4 | Alias-normalized exact match |
| **Star Rating** | `f-star-rating` | Comma-separated (e.g., `4,5`) | Sorted-set equality |
| **Price Min** | `f-price-min` | Integer (dollars) | Exact match |
| **Price Max** | `f-price-max` | Integer (dollars) | Exact match |
| **Amenities** | `f-amenities` | Comma-separated codes | Sorted-set equality |
| **Guest Rating** | `f-guest-rating` | Numeric minimum (e.g., `8`) | Exact match |
| **Payment Type** | `paymentType` | `FREE_CANCELLATION`, `PAY_LATER` | Uppercase exact match |

### Alternative Date Parameters

| Parameter | Format | Priority |
| :--- | :--- | :--- |
| `startDate` | `YYYY-MM-DD` | Primary (browser-verified) |
| `d1` | `YYYY-M-D` | Alternative |
| `checkIn` / `checkin` | `YYYY-MM-DD` | Legacy |
| `endDate` | `YYYY-MM-DD` | Primary |
| `d2` | `YYYY-M-D` | Alternative |
| `checkOut` / `checkout` | `YYYY-MM-DD` | Legacy |

All date formats are normalized to `YYYY-MM-DD` by the parser.

---

## 4. Sort Options (Browser-Verified)

| UI Label | `sort` Value | Description |
| :--- | :--- | :--- |
| Recommended | `RECOMMENDED` | Default sort (relevance) |
| Price: low to high | `PRICE_LOW_TO_HIGH` | Cheapest first |
| Price: high to low | `PRICE_HIGH_TO_LOW` | Most expensive first |
| Distance from downtown | `DISTANCE` | Closest to city center |
| Guest rating | `GUEST_RATING` | Highest guest reviews |
| Star rating | `STAR_RATING_HIGHEST_FIRST` | Highest star rating first |
| Review score | `REVIEW` | Best review scores |

### Alias Resolution

The verifier also accepts these aliases from agent URLs:

| Alias | Normalized To |
| :--- | :--- |
| `recommended` | `RECOMMENDED` |
| `price`, `price_low_to_high`, `lowest_price`, `cheapest` | `PRICE_LOW_TO_HIGH` |
| `price_high_to_low`, `highest_price`, `most_expensive` | `PRICE_HIGH_TO_LOW` |
| `distance`, `closest` | `DISTANCE` |
| `review`, `review_score`, `best_reviewed` | `REVIEW` |
| `guest_rating`, `top_rated` | `GUEST_RATING` |
| `star_rating`, `star_rating_highest_first`, `stars` | `STAR_RATING_HIGHEST_FIRST` |

---

## 5. Star Rating Filter (Browser-Verified)

Star ratings are passed as comma-separated values:

```
f-star-rating=4,5     ← 4-star AND 5-star
f-star-rating=3,4,5   ← 3, 4, AND 5-star
f-star-rating=5       ← 5-star only
```

The verifier normalizes to a **sorted list** and compares order-independently.

---

## 6. Price Filter (Browser-Verified)

Prices are in **DOLLARS** (not cents):

```
f-price-min=100&f-price-max=300   ← $100 to $300 per night
f-price-min=50                     ← $50 minimum
f-price-max=200                    ← $200 maximum
```

The verifier compares prices as **exact integers**.

---

## 7. Children Encoding (Browser-Verified)

### RoomIndex_Age Format (Primary)

Children are encoded with their room assignment and age:

```
children=1_5        ← 1 child age 5 in room 1
children=1_5,1_10   ← 2 children ages 5 and 10 in room 1
children=1_5,2_8    ← child age 5 in room 1, child age 8 in room 2
```

### Legacy Format

```
childrenAges=5,10   ← 2 children ages 5 and 10 (no room assignment)
```

The verifier extracts ages from both formats, sorts them, and compares as sorted lists.

---

## 8. Multi-Room Adults (Browser-Verified)

For multiple rooms, adults are comma-separated:

```
adults=2         ← 2 adults, 1 room
adults=2,1,1     ← Room 1: 2 adults, Room 2: 1 adult, Room 3: 1 adult (4 total)
```

The verifier sums multi-room adults for comparison and infers room count.

---

## 9. Amenities Filter

Amenities are passed as comma-separated uppercase codes:

```
f-amenities=WIFI,POOL,FREE_BREAKFAST
```

Common amenity codes:

| Code | Description |
| :--- | :--- |
| `WIFI` | Free WiFi |
| `POOL` | Swimming pool |
| `FREE_BREAKFAST` | Complimentary breakfast |
| `FREE_PARKING` | Free parking |
| `PET_FRIENDLY` | Pets allowed |
| `SPA` | Spa services |
| `GYM` | Fitness center |
| `RESTAURANT` | On-site restaurant |
| `AIR_CONDITIONING` | A/C |
| `KITCHEN` | Kitchen/kitchenette |

The verifier compares as **sorted sets** (order-independent).

---

## 10. Payment Type Filter

| UI Label | `paymentType` Value |
| :--- | :--- |
| Free cancellation | `FREE_CANCELLATION` |
| Pay later | `PAY_LATER` |

---

## 11. Guest Rating Filter

Minimum guest rating threshold:

```
f-guest-rating=8    ← Show only 8.0+ rated properties
f-guest-rating=7    ← Show only 7.0+ rated properties
```

---

## 12. Domain Variations

The verifier accepts **all** valid Hotels.com domains:

| Domain | Accepted | Description |
| :--- | :---: | :--- |
| `hotels.com` | ✅ | Primary (no www) |
| `www.hotels.com` | ✅ | Standard desktop |
| `in.hotels.com` | ✅ | India regional |
| `uk.hotels.com` | ✅ | UK regional |
| `de.hotels.com` | ✅ | Germany regional |
| `*.hotels.com` | ✅ | Any subdomain |
| `fakehotels.com` | ❌ | Not a subdomain |
| `booking.com` | ❌ | Different site |
| `expedia.com` | ❌ | Different site (same group) |

### Domain Validation Rules

1. **Exact match** against known domains: `hotels.com`, `www.hotels.com`
2. **Regional match**: known regional subdomains (`in.`, `uk.`, `de.`, etc.)
3. **Subdomain match**: any domain ending in `.hotels.com`
4. **Rejection**: domains that don't match the above rules

---

## 13. Ignored Parameters

These parameters encode session state, UI preferences, or tracking data.
They do **not** affect search semantics and are excluded from comparison:

### Tracking & Attribution (Ignored)
`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`,
`gclid`, `msclkid`, `ref`, `semcid`, `semdtl`

### Session / UI State (Ignored)
`locale`, `currency`, `siteid`, `tpid`, `eapid`, `rfrr`,
`latLong`, `theme`, `userIntent`, `selected`, `searchId`,
`propertyId`, `pwaDialogNested`, `mapBounds`, `neighborhood`,
`flexibility`, `pos`, `referrerUrl`

Extra parameters in the agent URL do not cause a mismatch.

---

## 14. Verifier Matching Rules

### Core Comparison Logic

| # | Field | Normalization | Comparison | Fail if GT has & Agent missing? |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Destination | URL-decode, lowercase, city-part only | Case-insensitive string match | ✅ Yes |
| 2 | Check-in date | Normalize to YYYY-MM-DD | Exact date match | ✅ Yes |
| 3 | Check-out date | Normalize to YYYY-MM-DD | Exact date match | ✅ Yes |
| 4 | Adults | Sum multi-room values | Exact integer-string match | ✅ Yes |
| 5 | Rooms | Raw or inferred from multi-room | Exact match | ✅ Yes |
| 6 | Children count | From RoomIdx_Age or legacy | Exact match | ✅ Yes |
| 7 | Children ages | Extract from RoomIdx_Age, sort | Sorted list equality | ✅ Yes |
| 8 | Sort order | Alias resolution (see §4) | Exact string match | ✅ Yes |
| 9 | Star rating | Parse comma-separated, sort | Sorted set equality | ✅ Yes |
| 10 | Price min | Parse as integer (dollars) | Exact integer match | ✅ Yes |
| 11 | Price max | Parse as integer (dollars) | Exact integer match | ✅ Yes |
| 12 | Amenities | Parse comma-separated, uppercase, sort | Sorted set equality | ✅ Yes |
| 13 | Guest rating | Raw value | Exact string match | ✅ Yes |
| 14 | Payment type | Uppercase | Exact string match | ✅ Yes |

### Precedence Rules

1. If ground truth specifies a field and agent **omits** it → **FAIL**
2. If ground truth **omits** a field → agent value is **ignored** (pass)
3. **No auto-pass loopholes**: every GT-specified field must be present and correct
4. Destination is compared as **city name only** (text before first comma)
5. Star rating and amenities compared as **sorted sets** — order does not matter
6. Children ages compared as **sorted lists** — order does not matter
7. First successful match across multi-GT URLs → **score = 1.0** (OR semantics)
8. All mismatches are logged with detailed diagnostic messages
9. Extra agent parameters not in GT are **ignored**
10. Tracking/session parameters (§13) are always ignored

### Matching Flow

```
Agent URL → Parse → Normalize
  ↓
GT URL → Parse → Normalize
  ↓
Compare (sequential — first failure stops):
  1. destination
  2. start_date
  3. end_date
  4. adults
  5. rooms
  6. children (count)
  7. children_ages (sorted list)
  8. sort
  9. star_rating (sorted set)
  10. price_min
  11. price_max
  12. amenities (sorted set)
  13. guest_rating
  14. payment_type
  ↓
All match? → score = 1.0
Any mismatch? → score = 0.0 (with mismatch field + details logged)
```

---

## 15. Homepage & Search Layout (Browser-Verified Jun 2026)

```
┌──────────────────────────────────────────────────────────────────┐
│  hotels.com                               [Sign in] [List prop] │
├──────────────────────────────────────────────────────────────────┤
│  [Stays] [Flights] [Cars] [Packages] [Things to do]            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Find your perfect stay                                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ 🔍 Going to [destination input]                       │       │
│  │ 📅 Dates [check-in] — [check-out]                    │       │
│  │ 👤 Travelers [adults] adults, [rooms] room            │       │
│  │                                    [Search]           │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
│  Popular destinations                                            │
│  ┌──────┬──────┬──────┬──────┬──────┐                           │
│  │ NYC  │Paris │Dubai │Cancun│Miami │                           │
│  └──────┴──────┴──────┴──────┴──────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 16. Search Results Page Layout (Browser-Verified)

```
┌──────────────────────────────────────────────────────────────────┐
│  hotels.com                                    [Sign in]         │
├──────────────────────────────────────────────────────────────────┤
│  [🔍 New York] [📅 Jul 1 — Jul 5] [👤 2 adults, 1 room]       │
├──────────────────────────────────────────────────────────────────┤
│  ┌─Filter pills──────────────────────────────────────────────┐  │
│  │ [Sort ▼] [Price ▼] [Star rating ▼] [Guest rating ▼]      │  │
│  │ [Amenities ▼] [Payment type ▼] [More filters]            │  │
│  └────────────────────────────────────────────────────────────┘  │
├──────────┬───────────────────────────────────────────────────────┤
│          │  X properties in New York                             │
│  [Map]   │  ┌────────────────────────────────────────────┐      │
│          │  │ [IMG]  Hotel Name ★★★★                      │      │
│          │  │        Location · 1.2 mi from center        │      │
│          │  │        8.6 Excellent (1,234 reviews)         │      │
│          │  │                          $189 per night      │      │
│          │  │                          [See availability]  │      │
│          │  └────────────────────────────────────────────┘      │
│          │  ┌────────────────────────────────────────────┐      │
│          │  │ [IMG]  Another Hotel ★★★★★                  │      │
│          │  │        ...                                   │      │
│          │  └────────────────────────────────────────────┘      │
└──────────┴───────────────────────────────────────────────────────┘
```

Key observations:
- **Filter pills** at the top (Sort, Price, Star rating, Guest rating, Amenities, etc.)
- Selecting any filter **updates the URL** with the filter parameter
- **Map view** on the left, listings on the right
- No login required for searching
- Results include star rating, guest rating, price per night, and distance
- Pagination at the bottom (not infinite scroll)

---

## Appendix A: Live URL Examples

### Basic Search
```
https://www.hotels.com/Hotel-Search?destination=New%20York&startDate=2026-07-01&endDate=2026-07-05&rooms=1&adults=2
```

### Search with Sort
```
https://www.hotels.com/Hotel-Search?destination=Paris&startDate=2026-08-10&endDate=2026-08-15&rooms=1&adults=2&sort=PRICE_LOW_TO_HIGH
```

### Search with Star Rating Filter
```
https://www.hotels.com/Hotel-Search?destination=London&startDate=2026-09-01&endDate=2026-09-03&rooms=1&adults=2&f-star-rating=4,5
```

### Search with Children
```
https://www.hotels.com/Hotel-Search?destination=Miami&startDate=2026-07-10&endDate=2026-07-15&rooms=1&adults=2&children=1_5,1_10
```

### Full Filter Combination
```
https://www.hotels.com/Hotel-Search
  ?destination=New%20York
  &startDate=2026-07-01
  &endDate=2026-07-05
  &adults=2
  &rooms=1
  &sort=PRICE_LOW_TO_HIGH
  &f-star-rating=4,5
  &f-amenities=WIFI,POOL
  &paymentType=FREE_CANCELLATION
```

### Multi-Room Search
```
https://www.hotels.com/Hotel-Search?destination=Tokyo&startDate=2026-10-01&endDate=2026-10-05&adults=2,1,1&rooms=3
```

### Regional Domain (India)
```
https://in.hotels.com/Hotel-Search?destination=Mumbai&startDate=2026-07-01&endDate=2026-07-03&rooms=1&adults=2
```

---

## Appendix B: Comparison with Related Domains

| Feature | Hotels.com | Expedia | Booking.com |
| :--- | :--- | :--- | :--- |
| **Owner** | Expedia Group | Expedia Group | Booking Holdings |
| **Search path** | `/Hotel-Search` | `/Hotel-Search` | `/searchresults.html` |
| **Destination param** | `destination` | `destination` | `ss` |
| **Date params** | `startDate`, `endDate` | `startDate`, `endDate` | `checkin`, `checkout` |
| **Sort param** | `sort` | `sort` | `order` |
| **Sort values** | `PRICE_LOW_TO_HIGH`, etc. | `PRICE_LOW_TO_HIGH`, etc. | `price`, etc. |
| **Star filter** | `f-star-rating=4,5` | Same | `nflt=class%3D5` |
| **Price filter** | `f-price-min`, `f-price-max` | Similar | `nflt=price=...` |
| **Children** | `children=1_5` (RoomIdx_Age) | `children=1_5` | `age=5` |
| **Adults** | `adults=2` (or `2,1` multi-room) | Same | `group_adults=2` |
| **Rooms** | `rooms=1` | `rooms=1` | `no_rooms=1` |
| **Region ID** | `regionId=2621` | `regionId=2621` | N/A |
| **Price encoding** | Dollars | Dollars | Local currency |
| **Login required** | No | No | No |
| **Verification type** | URL-based | URL-based | URL-based |

---
