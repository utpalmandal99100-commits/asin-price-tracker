# Price Tracker: Amazon India, Myntra, Nykaa, Tata CLiQ

Enter an ASIN, Myntra Style ID, Nykaa or Tata CLiQ Product ID, or a product URL. The app detects the platform, gets the product's details, helps you find the same product on the other three platforms, and shows every listing in one comparison table with the lowest verified price highlighted. Products are saved, prices can be refreshed, and **Download Excel** exports everything.

Every price carries where it came from and when it was verified. Nothing is scraped and no price is ever made up: a listing without a verified price shows "Not verified" and a blank price.

## Data access (checked October 2026)

| Platform | Access in this app | What you need |
|---|---|---|
| Amazon India | **Live**, via the official [Amazon Creators API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation) (the successor of PA-API 5, which now returns `AccessDenied`). Fetches name, brand, MRP (the "M.R.P." saving basis), selling price and stock, and searches Amazon to suggest matches. | An Amazon Associates India account with Creators API credentials (free). Amazon has historically required recent qualifying sales before granting API access; Associates Central > Tools > Creators API shows whether your account is eligible. |
| Myntra | **Manual verification.** No official public product or price API exists. Its affiliate programmes (through networks such as Cuelinks or FlexOffers) give tracking links, not price data. | Nothing. You open the product page from the dashboard and enter the price you see; it is saved with the time you checked. |
| Nykaa | **Manual verification.** Same situation: no official public product API. | Nothing (as above). |
| Tata CLiQ | **Manual verification.** Same situation: no official public product API. | Nothing (as above). |

Third-party "Myntra/Nykaa/Tata CLiQ APIs" sold by scraping vendors (Apify actors, Bright Data, Actowiz and similar) collect data by scraping those sites, not with the platforms' permission, so they are deliberately **not** integrated. The authorised route to automate these three is a direct data or partner agreement with each platform; once you have one, add an adapter next to `tracker/amazon.py`.

## Price status

| Status | Meaning | Used for "Lowest"? |
|---|---|---|
| Verified · API | Returned by the Amazon Creators API at the time shown | Yes |
| Verified · manual | You checked the product page and entered it at the time shown | Yes, until it is older than `MANUAL_PRICE_MAX_AGE_HOURS` (24h by default) |
| Stale | A manual check older than that limit | No |
| Unavailable | Out of stock or no offer at the last check | No |
| Not verified | No verified price yet | No |
| Refresh failed | The last API call failed; the last verified price is shown only as "last verified" | No |

## Matching

Matches are scored on brand, product name, EAN/model code and variant (pack size such as 100 ml vs 1 L, count, clothing/shoe size, colour). A different variant caps the score below the confirmation threshold, so a 125 ml and a 250 ml bottle are never treated as the same product.

- When Amazon access is configured and the source product is on another platform, the best Amazon result is attached as a **suggested match**. It is not used for "Lowest" until you click **Confirm match**. **Find via API** lists more Amazon candidates with their scores.
- For Myntra, Nykaa and Tata CLiQ, each product shows a **Search** link that opens that platform's own search for the brand and name. Paste the matching URL or ID, then use **Enter price**.

## Run it

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in Amazon credentials (optional)
python app.py
```

Open http://127.0.0.1:5000. Data is stored in `data/tracker.db` (SQLite).

### Amazon credentials

1. Sign in to [Amazon Associates India](https://affiliate-program.amazon.in/) (join if needed).
2. Go to **Tools > Creators API** and create credentials. Copy the Credential ID, Credential Secret and the **version** shown with them.
3. Put them in `.env` with your tracking ID (`yourname-21`) as `AMAZON_PARTNER_TAG`, then restart the app.

Without credentials the app still works: Amazon listings can be priced manually like the others.

## Excel export

**Download Excel** (or `GET /api/export.xlsx`) produces a workbook with:

- **Comparison**: one row per listing with Product Name, Platform, Platform Product ID, MRP, Current Selling Price, a Lowest Price flag (row highlighted), Price Status, Last Verified (IST), Data Source, match state and score, and the product URL. Unverified, stale and failed prices are left blank in the price column.
- **Price History**: every verified price and status change with its timestamp.
- **Read Me**: what each status means.

## Requests and access rules

- Amazon calls go only to the official API, are batched (10 ASINs per call) and throttled to 1 per second. "Refresh all" skips listings checked in the last `MIN_REFRESH_MINUTES`.
- The app never requests pages from Myntra, Nykaa, Tata CLiQ or amazon.in. Links open in your own browser.

## Tests

```bash
python -m pytest
```
