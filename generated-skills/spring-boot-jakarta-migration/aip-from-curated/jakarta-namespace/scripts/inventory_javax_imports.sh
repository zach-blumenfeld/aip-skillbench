#!/usr/bin/env bash
# Inventory every javax.* import in a Java source tree that needs migration to
# the jakarta.* namespace for Spring Boot 3+. JDK-internal packages (javax.sql,
# javax.crypto, javax.net, javax.security, javax.naming, javax.xml.parsers,
# javax.xml.transform, javax.management) are excluded — they stay on javax.
#
# Usage:
#   scripts/inventory_javax_imports.sh <path-to-src-root>
#
# Output (stdout): one row per match.
#   <file>:<line>\t<group>\t<import-statement>
# Where <group> is one of:
#   persistence | validation | servlet | annotation | transaction |
#   ws.rs | mail | jms | xml.bind | other
#
# Exit 0 if scan completed (even with zero matches). Exit 1 on usage error.
# stderr carries a one-line summary count.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-src-root>" >&2
  exit 1
fi

ROOT="$1"
if [[ ! -d "$ROOT" ]]; then
  echo "error: not a directory: $ROOT" >&2
  exit 1
fi

GREP=${GREP:-grep}

classify() {
  # Reads "file:line:content" from stdin; emits "file:line\tgroup\timport-stmt".
  # POSIX awk has no \b word boundary; use explicit alternations on `.` or end-of-string.
  awk -F: '
    {
      file=$1; line=$2;
      content=$3;
      for (i=4; i<=NF; i++) content=content ":" $i;
      gsub(/^[ \t]+/, "", content);

      # Only consider import statements.
      if (content !~ /^import[ \t]+javax\./) next;

      # Extract the subpackage after "javax.".
      sub_pkg=content;
      sub(/^import[ \t]+javax\./, "", sub_pkg);
      sub(/[ \t;].*$/, "", sub_pkg);
      sub(/;$/, "", sub_pkg);

      # Skip JDK-internal javax.* packages. Match either "<pkg>" exactly or "<pkg>." prefix.
      if (sub_pkg ~ /^(sql|crypto|net|security|naming|management)(\.|$)/) next;
      if (sub_pkg ~ /^xml\.(parsers|transform|stream|xpath|datatype|namespace|validation|catalog)(\.|$)/) next;

      group="other";
      if (sub_pkg ~ /^persistence(\.|$)/) group="persistence";
      else if (sub_pkg ~ /^validation(\.|$)/) group="validation";
      else if (sub_pkg ~ /^servlet(\.|$)/) group="servlet";
      else if (sub_pkg ~ /^annotation(\.|$)/) group="annotation";
      else if (sub_pkg ~ /^transaction(\.|$)/) group="transaction";
      else if (sub_pkg ~ /^ws\.rs(\.|$)/) group="ws.rs";
      else if (sub_pkg ~ /^mail(\.|$)/) group="mail";
      else if (sub_pkg ~ /^jms(\.|$)/) group="jms";
      else if (sub_pkg ~ /^xml\.bind(\.|$)/) group="xml.bind";
      else if (sub_pkg ~ /^inject(\.|$)/) group="inject";
      else if (sub_pkg ~ /^enterprise(\.|$)/) group="enterprise";
      else if (sub_pkg ~ /^ejb(\.|$)/) group="ejb";
      else if (sub_pkg ~ /^json(\.|$)/) group="json";
      else if (sub_pkg ~ /^batch(\.|$)/) group="batch";

      snippet=content;
      sub(/;$/, ";", snippet);
      if (length(snippet) > 200) snippet=substr(snippet, 1, 197) "...";
      printf "%s:%s\t%s\t%s\n", file, line, group, snippet;
    }
  '
}

matches=$("$GREP" -rEnH --include='*.java' \
  -e '^[[:space:]]*import[[:space:]]+javax\.' \
  "$ROOT" 2>/dev/null || true)

if [[ -z "$matches" ]]; then
  echo "scanned: $ROOT — 0 javax imports" >&2
  exit 0
fi

out=$(printf "%s\n" "$matches" | classify)

if [[ -z "$out" ]]; then
  echo "scanned: $ROOT — only JDK-internal javax imports (no migration needed)" >&2
  exit 0
fi

count=$(printf "%s\n" "$out" | wc -l | tr -d ' ')
printf "%s\n" "$out"
echo "scanned: $ROOT — $count migration-candidate import(s)" >&2
