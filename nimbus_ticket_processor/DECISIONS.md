# Decisions Document

This document outlines the architectural, structural, and prompt engineering decisions made for the Nimbus Retail Ticket Processor.

## 1. Assumptions About Data and Process
- **Dynamic Columns:** We assume that CSV structure might evolve, so we use `csv.DictReader.get()` to gracefully ignore unknown columns and handle missing optional columns.
- **Repeat Customers:** We track the count of previous contacts from the same email in the current batch and feed this number into the Claude prompt. This allows the LLM to identify when a customer is repeatedly escalating an unresolved issue.
- **Mixed Languages:** The Claude API (Claude 3.5 Sonnet) is capable of understanding multiple languages implicitly. We rely on the model to read Spanish tickets, classify them according to our English taxonomy, and output the JSON in English.

## 2. Taxonomy and Urgency Definitions
- **Categories:** `Refund`, `Delivery`, `Account`, `Product Question`, `Technical Issue`, `Other`, `Spam`. This covers the primary eCommerce concerns.
- **Urgency Levels:**
  - `Low`: General inquiries or spam.
  - `Medium`: Standard issues requiring action but without critical time sensitivity.
  - `High`: Immediate attention needed (legal, fraud, severe delays, angry repeat customers).
- **Escalation Reasoning:** We specifically ask the model for a boolean `escalate` flag and a string `escalation_reason`. If it flags it, it must provide a clear, sentence-long justification based on the rules (e.g., "Customer threatens lawyer after three unresolved complaints.").

## 3. Dealing With Prompt Injections
The dataset contains a malicious row (Ticket #43) attempting to redefine the model's behavior ("Disregard your previous instructions"). 
- **Decision:** We wrap all user-generated content (Subject and Message) inside `<ticket_content>` XML tags in our prompt.
- **Rationale:** We instruct Claude to treat everything inside those tags strictly as data to be classified, not as instructions. This structural separation is the industry standard for preventing prompt leakage in LLM pipelines.

## 4. Date Parsing
- **Decision:** We use a deterministic list of expected date formats first, iterating through them before falling back to `dateutil.parser`.
- **Rationale:** `dateutil` can incorrectly guess US vs. EU format for ambiguous dates like `05/01/2026`. Iterating through known formats provides predictable behavior.

## 5. Caching and Cost Reduction
- **Caching Mechanism:** We cache responses locally to `cache.json` using a composite key: the hash of the ticket ID, subject, and message.
- **Refresh Logic:** We also store a timestamp. If a cached entry is older than 24 hours, it is reprocessed. This ensures urgency classifications don't remain stale if a ticket remains unresolved.
- **Spam Pre-filtering:** We use a lightweight Python function to search for obvious spam phrases ("you have won", "click here now"). Tickets matching this are flagged as Spam locally without ever hitting the Claude API, saving costs.

## 6. Error Handling (Resilience)
- **API Errors:** The script implements a retry loop with exponential backoff to handle 429 Rate Limit or 5xx Outage errors.
- **Malformed JSON:** We request JSON explicitly in the prompt, but also use a Regex fallback to extract JSON if Claude surrounds it in markdown blocks. If JSON parsing still fails, we default to a safe classification (Category: Other, Urgency: Medium) and log the error, ensuring the script continues processing the rest of the CSV.
- **Report Generation:** The report aggregation is done using standard Python dictionaries and strings. We do not use the LLM to generate the final summary paragraph, as that would incur an unnecessary additional API call and cost.

## 7. Cost Estimation
- **Sample Run:** The dataset contains ~40 valid tickets. Assuming ~150 tokens in and ~50 tokens out per ticket:
  - Input: 150 * 40 = 6,000 tokens ($0.018 at $3/1M)
  - Output: 50 * 40 = 2,000 tokens ($0.03 at $15/1M)
  - Total Sample Cost: ~$0.05
- **10x Volume (400 tickets):** ~$0.50
- This is highly cost-efficient and well within the <= $2 budget.

## 8. What I Would Do With More Time
- Implement asynchronous API calls (e.g., using `asyncio` and `httpx`) to process tickets concurrently, drastically reducing execution time for large datasets.
- Persist cache to a real database (SQLite/PostgreSQL) instead of a JSON file for better concurrency and scaling.
- Connect to an actual ticketing system API (Zendesk, Intercom) to pull down tickets and push tags/classifications directly back to the platform.
