The filled offer letter at `{output_file}` is not ready. Fix it so it is a finished
document, then answer with `repair_notes`.

Template: `{template_path}`
Data file: `{data_path}`
Required output path: `{output_path}`

Issues the fill script reported:
{issues}

Conditional blocks and how they were resolved (`included: null` means the data flag was
missing or not a clear yes/no):
{conditionals}

Current letter text (body, then `[hdr]` header and `[ftr]` footer lines):
{letter_text}

Do this:
1. Open the data file and settle each issue from the data: find the field behind an
   unresolved IF_X conditional marker (yes-like keeps the block, no-like removes it), the data key
   behind an unmatched placeholder (names may differ in case or wording), or the record
   to use when the file holds several hires.
2. Rerun the script (`scripts/fill_template.py` in the {meta.name} skill folder) from the template with the fixes, writing to `{output_path}`:
   `python3 scripts/fill_template.py --template {template_path} --data {data_path} --output {output_path} [--condition X=yes|no] [--map PLACEHOLDER=data_key] [--record N]`
   Repeat until it prints `status: complete`. Only if the script cannot express the fix,
   edit the `.docx` with python-docx following the reference.
3. Never invent a value the data does not hold; if one is truly absent, leave that gap,
   and say so in your notes.
4. Re-open the output and confirm no double-brace template markup remains in body, tables, header or footer.

`repair_notes`: what was wrong, what you changed (exact rerun command), and anything left
unresolved.
