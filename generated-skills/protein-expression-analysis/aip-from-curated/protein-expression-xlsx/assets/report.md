# Report the protein expression analysis

Output workbook: {output_path}
Verification: {verify_status}
Data scale used: {data_scale}; standard deviation: {stdev_kind}

Per-protein results:
{results}

Ranked by |Log2 FC|:
{top_regulated}

Build notes: {build_notes}

Write `final_summary`, a short plain-text report for the requester:
1. Where the results were written (the file path) and which regions were filled: the lookup block, the statistics block (one column per protein), the fold-change table, and the ranking table if one was added.
2. Method in one or two lines: values looked up by Protein_ID and sample name with INDEX/MATCH; blank source cells stay blank and are excluded from means and SDs; the data are {data_scale}, so for log2 data Log2 FC = treated mean − control mean and Fold Change = 2^Log2 FC (for linear data Fold Change = treated mean / control mean and Log2 FC = log2 of it); SD is the sample SD (n−1) unless population was chosen.
3. The top up- and down-regulated proteins with gene symbol, Log2 FC and fold change. Name the proteins whose SD or fold change is blank because a group had too few values; treat fold changes built on one or two values as weak.
4. If verification is not `ok`, say so plainly and what remains (e.g. formulas not yet recalculated, so cached values are empty until the file is opened in Excel/LibreOffice).

Use the numbers in the state; do not round them further than 3–4 significant digits in prose and do not invent statistics (p-values, q-values) that were not computed.
