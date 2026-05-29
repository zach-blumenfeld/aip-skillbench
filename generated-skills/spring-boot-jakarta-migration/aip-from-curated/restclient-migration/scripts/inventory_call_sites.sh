#!/usr/bin/env bash
# Inventory every RestTemplate call site in a Java source tree.
#
# Usage:
#   scripts/inventory_call_sites.sh <path-to-src-root>
#
# Output (stdout): one row per match.
#   <file>:<line>\t<kind>\t<snippet>
# Where <kind> is one of:
#   import         — `import org.springframework.web.client.RestTemplate;`
#   field-decl     — declaration of a RestTemplate field/var
#   constructor    — `new RestTemplate(`
#   getForEntity   — RestTemplate#getForEntity / getForObject
#   postForEntity  — RestTemplate#postForEntity / postForObject / postForLocation
#   put            — RestTemplate#put
#   delete         — RestTemplate#delete
#   exchange       — RestTemplate#exchange
#   execute        — RestTemplate#execute
#   error-handler  — setErrorHandler / ResponseErrorHandler usage
#   other          — any other line containing `RestTemplate` or `restTemplate.`
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

# Pick a grep that supports -E -H -n; macOS BSD grep is fine.
GREP=${GREP:-grep}

classify() {
  # Reads "file:line:content" from stdin; emits "file:line\tkind\tsnippet".
  awk -F: '
    {
      file=$1; line=$2;
      # Reassemble the content (may itself contain colons).
      content=$3;
      for (i=4; i<=NF; i++) content=content ":" $i;
      raw=content;
      gsub(/^[ \t]+/, "", content);

      kind="other";
      if (content ~ /^import[ \t]+org\.springframework\.web\.client\.RestTemplate[ \t]*;/) kind="import";
      else if (content ~ /new[ \t]+RestTemplate[ \t]*\(/) kind="constructor";
      else if (content ~ /(private|protected|public|final|static)[ \t].*RestTemplate[ \t]+[A-Za-z_][A-Za-z0-9_]*/) kind="field-decl";
      else if (content ~ /RestTemplate[ \t]+[A-Za-z_][A-Za-z0-9_]*[ \t]*[=;]/) kind="field-decl";
      else if (content ~ /\.getForEntity[ \t]*\(/ || content ~ /\.getForObject[ \t]*\(/) kind="getForEntity";
      else if (content ~ /\.postForEntity[ \t]*\(/ || content ~ /\.postForObject[ \t]*\(/ || content ~ /\.postForLocation[ \t]*\(/) kind="postForEntity";
      else if (content ~ /\.put[ \t]*\(/ && content ~ /(restTemplate|RestTemplate)/) kind="put";
      else if (content ~ /\.delete[ \t]*\(/ && content ~ /(restTemplate|RestTemplate)/) kind="delete";
      else if (content ~ /\.exchange[ \t]*\(/ && content ~ /(restTemplate|RestTemplate)/) kind="exchange";
      else if (content ~ /\.execute[ \t]*\(/ && content ~ /(restTemplate|RestTemplate)/) kind="execute";
      else if (content ~ /setErrorHandler[ \t]*\(/ || content ~ /ResponseErrorHandler/) kind="error-handler";

      # Trim long snippet for readability.
      snippet=content;
      if (length(snippet) > 200) snippet=substr(snippet, 1, 197) "...";
      printf "%s:%s\t%s\t%s\n", file, line, kind, snippet;
    }
  '
}

# Match any line referencing RestTemplate (class) or `restTemplate.` (instance).
matches=$("$GREP" -rEnH --include='*.java' \
  -e 'RestTemplate' \
  -e 'restTemplate\.' \
  "$ROOT" 2>/dev/null || true)

if [[ -z "$matches" ]]; then
  echo "scanned: $ROOT — 0 matches" >&2
  exit 0
fi

count=$(printf "%s\n" "$matches" | wc -l | tr -d ' ')
printf "%s\n" "$matches" | classify
echo "scanned: $ROOT — $count match(es)" >&2
