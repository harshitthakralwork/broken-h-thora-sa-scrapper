# SparkXFlow — Lead Discovery Connector & Provider Audit

An empirical audit of all 11 discovery connectors and data providers available in the SparkXFlow platform.

---

## 1. Provider Status Matrix

| Connector Name | Canonical Keys / Aliases | Category | Status Classification | Authentication Required | Notes & License |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Wikidata SPARQL** | `wikidata_sparql`, `wikidata`, `knowledge_graph` | Open Knowledge Graph | **LIVE AND VERIFIED** | None (Public CC0) | Free W3C SPARQL endpoint (`query.wikidata.org`). Live tested for Indian tech, logistics, and healthcare enterprises. |
| **OpenStreetMap Overpass** | `osm_overpass`, `overpass`, `openstreetmap` | Geospatial Business Registry | **LIVE AND VERIFIED** | None (Public ODbL) | Queries public Overpass API instances for real commercial venues with Indian bounding boxes. |
| **CSV File Import** | `csv_file` | Structured File Import | **LIVE AND VERIFIED** | None (User-Supplied) | Parses user-uploaded CSV spreadsheets with duplicate checks and provenance tracking. |
| **Public Website Crawler** | `website_crawler`, `crawler` | Direct Web Research | **RESEARCH-ONLY** | None | Crawls verified public company websites in an SSRF-safe sandbox. **Not an independent discovery provider.** |
| **OutLead Bulk Maps** | `outlead_bulk_maps`, `outlead`, `bulk_maps`, `google_maps` | Bulk Business Discovery | **IMPLEMENTED BUT UNCONFIGURED** | `GOOGLE_PLACES_API_KEY` / `SERPAPI_API_KEY` | Implements OutLead-inspired batch Cartesian discovery. Bot bypass is strictly disabled. |
| **India Open Gov Data (OGD)** | `india_ogd` | Official Public Registry | **IMPLEMENTED BUT UNCONFIGURED** | `DATA_GOV_IN_API_KEY` | Connects to official `data.gov.in` company master resources. |
| **Permitted Directory** | `public_directory` | Public Business Directory | **IMPLEMENTED BUT UNCONFIGURED** | `DIRECTORY_API_ENDPOINT` | Configurable webhook bridge for approved public directory feeds. |
| **Web Query Index** | `web_query` | Search Engine Index | **IMPLEMENTED BUT UNCONFIGURED** | `GOOGLE_SEARCH_API_KEY` / `SERPAPI_API_KEY` | Discovers businesses via search index queries. Requires API key. |
| **UK Companies House** | `uk_companies_house` | Official Registry | **IMPLEMENTED BUT UNCONFIGURED** | `COMPANIES_HOUSE_API_KEY` | Free REST API for UK registered entities. |
| **SEC EDGAR** | `sec_edgar` | Public Financial Filings | **IMPLEMENTED BUT UNCONFIGURED** | User-Agent Email | Public US corporate filing registry. |
| **OpenCorporates** | `opencorporates` | Global Company Database | **IMPLEMENTED BUT UNCONFIGURED** | `OPENCORPORATES_API_KEY` | Global corporate entity search. |

---

## 2. Independent Discovery Provider Validation

### Verified Live Provider: Wikidata SPARQL Knowledge Graph
- **Endpoint:** `https://query.wikidata.org/sparql`
- **License:** Creative Commons CC0 1.0 Universal Public Domain Dedication
- **Empirical Test:**
  - **Query:** Incorporated commercial entities with headquarters in Bengaluru, Karnataka, India (`Q1355` / `Q1150031`)
  - **HTTP Status:** 200 OK
  - **Verified Businesses Returned:**
    1. *Bharat Electronics Limited* (`https://www.bel-india.in/`) — URI: `http://www.wikidata.org/entity/Q3630918`
    2. *National Aerospace Laboratories* (`http://www.nal.res.in/`) — URI: `http://www.wikidata.org/entity/Q3595204`
    3. *Centre for Internet and Society* (`http://cis-india.org/`) — URI: `http://www.wikidata.org/entity/Q2801619`
- **Confirmation:** Genuine real-world business entities with official domain websites and Wikidata entity attribution. Zero synthetic records.

---

## 3. Crawler vs. Discovery Tool Boundary

> [!NOTE]
> Per SparkXFlow architectural guidelines, **`website_crawler` is strictly a research and evidence extraction engine**, not an autonomous discovery tool. It requires a known website URL (supplied via discovery connectors or manual entry) before it can analyze a website. It is never misrepresented as an independent discovery source.

