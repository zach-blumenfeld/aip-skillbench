# Protein expression fold-change notes

Load when deciding the data scale, judging an unusual layout, or interpreting results for the report.

## Data scale
- Proteomics tables such as CCLE TMT (`..._TenPx##` sample names = TMT 10-plex batches) hold log2 relative abundances: values centred near 0, roughly −15 to +8, about half negative. These are already log2. Never take the log again and never divide means: a ratio of two negative means is meaningless.
  - Log2 FC = mean(treated log2) − mean(control log2); Fold Change = 2^Log2 FC.
- Raw or normalised intensities/spectral counts are linear: all positive, often 1e3–1e9.
  - Fold Change = mean(treated) / mean(control); Log2 FC = log2(Fold Change).
- Log2 FC > 0 is up-regulated in treated, < 0 down-regulated; |Log2 FC| = 1 is a two-fold change, the usual cut-off for "strongly regulated".

## Missing values
- Blank cells in the data sheet are missing measurements, not zeros. Keep them blank in the lookup block; AVERAGE, STDEV and COUNT ignore blank and "" cells. Writing 0 instead shifts the mean toward 0 and inflates the SD.
- A group with no values has no mean, so no fold change; fewer than 2 values gives no sample SD. Leave those cells "" rather than letting them show #DIV/0!.
- Fold changes resting on one or two values per group are unreliable; flag them in the report.

## Standard deviation
- Replicate samples → sample SD (n−1): Excel STDEV (= STDEV.S). Use population SD (STDEVP) only when the task asks for it.
- Either way, an SD from a single value is left blank (STDEVP would return 0, which looks precise but is not).

## Ranking "top regulated"
- Rank by |Log2 FC|, largest first; report direction (Up/Down) separately. Exact ties are broken by sheet order so ranks stay unique.
- When the template has no Step 4 region, the ranking goes two rows under the fold-change table: per-protein columns A:F (ID, gene, Log2 FC, |Log2 FC|, Rank, Direction) and a sorted strongest-first list in H:L. Sheet instruction ranges for Step 4 (e.g. H43:L52) are usually as stale as the others, so they are not used as anchors.
- No p-values are computed here; do not call proteins "significant".
