Extract the facts for a California small claims Plaintiff's Claim (form SC-100) from the case below. Return one JSON object under the output key `sc100_case`, shaped like this schema (each value here describes what goes in that slot):

{assets[sc100_case_schema]}

Case description / task statement:

{case_description}

Rules:
- Use only facts the case states or that follow directly from them. Leave a slot empty ("") when the case does not supply it; never invent addresses, phones, emails, court names, or dates. An empty slot leaves its form field empty, which is what the task wants for unmentioned fields.
- Split each address into street, city, state (2-letter), and ZIP. Copy names, phone numbers, and emails exactly as written.
- Dates: give every date as YYYY-MM-DD (convert "January 19, 2026" to 2026-01-19); a script reformats them to the required output format ({date_format}).
- Item 3b: a single date of the event goes in incident_date; a span ("from X until Y") goes in period_start/period_through with incident_date empty.
- Write why_owed and how_calculated as short, factual sentences in the plaintiff's voice that reuse the case's key terms (amount, the document, what the defendant failed to do). Keep each under about 400 characters so it fits the form.
- The first plaintiff listed is the person filing ("I am ..."). Add a second plaintiff only if the case names one.
- Read references/sc100-guide.md if any slot is unclear.
