#!/usr/bin/env bash
# migrate.sh - deterministic Spring Boot 2.x -> 3.x rewrites for a Maven project.
#
# Requires: bash >= 4, find, grep, sed, awk (POSIX/mawk is enough), mktemp. No python, no network.
# Usage:    bash scripts/migrate.sh <project_dir> [--boot-version 3.2.0] [--java-version 21]
#                                   [--jjwt-version 0.12.3] [--dry-run]
#
# What it rewrites (idempotent; run it again and it reports 0 changes):
#   pom.xml   : spring-boot-starter-parent / spring-boot-dependencies / spring-boot.version -> --boot-version
#               java.version, maven.compiler.{source,target,release}, maven-compiler-plugin source/target/release
#               removes javax.xml.bind:jaxb-api, com.sun.xml.bind:jaxb-impl|jaxb-core,
#                       javax.activation:activation|javax.activation-api
#               io.jsonwebtoken:jjwt -> jjwt-api + jjwt-impl(runtime) + jjwt-jackson(runtime); bumps modular jjwt
#               javax.* API artifacts -> jakarta.* coordinates (version left to Boot's BOM)
#               mysql:mysql-connector-java -> com.mysql:mysql-connector-j; org.hibernate:hibernate-core -> org.hibernate.orm
#               drops explicit lombok version (Boot 3.2 manages a Java-21-safe one)
#               adds jakarta.xml.bind-api + jaxb-runtime only if the code still uses jakarta.xml.bind
#   *.java/*.kt/*.groovy under src/ : Java EE javax.* -> jakarta.* (JDK javax.* untouched),
#               @EnableGlobalMethodSecurity -> @EnableMethodSecurity, .antMatchers(/.mvcMatchers( -> .requestMatchers(,
#               .authorizeRequests( -> .authorizeHttpRequests(, HQL "update from X" -> "update X"
#   src/**/application*.properties|yml|yaml : javax.persistence.* keys, renamed Hibernate dialects,
#               spring.redis.* -> spring.data.redis.*, server.max-http-header-size
#   src/**/persistence.xml|orm.xml : JPA XML namespace -> jakarta, javax.persistence.* properties
# What it does NOT do (client tasks in SKILL.md): WebSecurityConfigurerAdapter -> SecurityFilterChain,
#   chained -> lambda DSL, RestTemplate -> RestClient, jjwt 0.9 -> 0.12 code API, Hibernate @Type/Criteria code.
set -euo pipefail

usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

PROJECT=""; BOOT="3.2.0"; JAVA="21"; JJWT="0.12.3"; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --boot-version) BOOT="$2"; shift 2;;
    --java-version) JAVA="$2"; shift 2;;
    --jjwt-version) JJWT="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    -h|--help) usage;;
    -*) echo "ERROR: unknown option $1" >&2; usage;;
    *) PROJECT="$1"; shift;;
  esac
done
[ -n "$PROJECT" ] || { echo "ERROR: project dir required" >&2; usage; }
[ -d "$PROJECT" ] || { echo "ERROR: $PROJECT is not a directory" >&2; exit 2; }
POM="$PROJECT/pom.xml"
[ -f "$POM" ] || { echo "ERROR: no pom.xml in $PROJECT (this script handles Maven projects; for Gradle apply the same changes by hand from references/pom-and-namespace.md)" >&2; exit 2; }
case "$BOOT" in 3.*) ;; *) echo "ERROR: --boot-version must be 3.x (got $BOOT)" >&2; exit 2;; esac
[ "$JAVA" -ge 17 ] 2>/dev/null || { echo "ERROR: --java-version must be >= 17 (got $JAVA)" >&2; exit 2; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
CHANGED=0
# apply <file> <newcontent-file> <label>: replace file if content differs, report it
apply() {
  if ! cmp -s "$1" "$2"; then
    CHANGED=$((CHANGED+1))
    echo "CHANGED $3: ${1#$PROJECT/}"
    diff -u "$1" "$2" | sed -n '3,$p' | grep -E '^[-+]' | sed 's/^/    /' | head -40 || true
    [ "$DRY" = 1 ] || cat "$2" > "$1"
  fi
}

# ---------------------------------------------------------------- Java / Kotlin / Groovy sources
# Whitelist of Java EE packages that moved to jakarta.*. JDK packages (javax.sql, javax.crypto, javax.net,
# javax.naming, javax.management, javax.security.auth, javax.xml.parsers, javax.transaction.xa,
# javax.annotation.processing, JSR-305 javax.annotation.Nullable/Nonnull ...) are deliberately absent.
EE_PKGS="persistence validation servlet transaction ws\.rs mail jms xml\.bind websocket inject activation ejb faces el json enterprise"
EE_ANNOT="PostConstruct PreDestroy Resource Resources Priority ManagedBean Generated security sql\.DataSourceDefinition"
SED_JAVA="$TMP/java.sed"
{
  echo 's/javax\.transaction\.xa\([.;]\)/@@JDK_TX_XA@@\1/g'
  for p in $EE_PKGS; do echo "s/javax\\.$p\\([.;]\\)/jakarta.$p\\1/g"; done
  for a in $EE_ANNOT; do echo "s/javax\\.annotation\\.$a\\([^A-Za-z0-9_]\\)/jakarta.annotation.$a\\1/g"; done
  echo 's/@@JDK_TX_XA@@/javax.transaction.xa/g'
  echo 's/EnableGlobalMethodSecurity/EnableMethodSecurity/g'
  echo 's/\.antMatchers(/.requestMatchers(/g'
  echo 's/\.mvcMatchers(/.requestMatchers(/g'
  echo 's/\.authorizeRequests(/.authorizeHttpRequests(/g'
  # HQL/JPQL: Hibernate 6 rejects the optional FROM in UPDATE statements (only at the start of a string literal)
  echo 's/\("[[:space:]]*\)\([Uu][Pp][Dd][Aa][Tt][Ee]\)[[:space:]]\{1,\}[Ff][Rr][Oo][Mm][[:space:]]\{1,\}/\1\2 /g'
} > "$SED_JAVA"

while IFS= read -r -d '' f; do
  sed -f "$SED_JAVA" "$f" > "$TMP/out"
  apply "$f" "$TMP/out" "source"
done < <(find "$PROJECT" -path '*/target' -prune -o -path '*/build' -prune -o -path '*/.git' -prune -o \
          -type f \( -name '*.java' -o -name '*.kt' -o -name '*.groovy' \) -print0)

# ---------------------------------------------------------------- application properties / yaml
SED_PROPS="$TMP/props.sed"
cat > "$SED_PROPS" <<'EOF'
s/javax\.persistence\./jakarta.persistence./g
s/org\.hibernate\.dialect\.MySQL5[0-9]*\(InnoDB\)*Dialect/org.hibernate.dialect.MySQLDialect/g
s/org\.hibernate\.dialect\.MySQL8Dialect/org.hibernate.dialect.MySQLDialect/g
s/org\.hibernate\.dialect\.MySQL57InnoDBDialect/org.hibernate.dialect.MySQLDialect/g
s/org\.hibernate\.dialect\.MariaDB[0-9]\{1,\}Dialect/org.hibernate.dialect.MariaDBDialect/g
s/org\.hibernate\.dialect\.PostgreSQL[0-9]\{1,\}Dialect/org.hibernate.dialect.PostgreSQLDialect/g
s/org\.hibernate\.dialect\.SQLServer20[0-9]\{2\}Dialect/org.hibernate.dialect.SQLServerDialect/g
s/org\.hibernate\.dialect\.Oracle[0-9]\{1,\}[a-z]*Dialect/org.hibernate.dialect.OracleDialect/g
s/^\([[:space:]]*\)spring\.redis\./\1spring.data.redis./
s/^\([[:space:]]*\)server\.max-http-header-size/\1server.max-http-request-header-size/
EOF
while IFS= read -r -d '' f; do
  sed -f "$SED_PROPS" "$f" > "$TMP/out"
  apply "$f" "$TMP/out" "config"
done < <(find "$PROJECT" -path '*/target' -prune -o -path '*/build' -prune -o -type f \
          \( -name 'application*.properties' -o -name 'application*.yml' -o -name 'application*.yaml' \
             -o -name 'bootstrap*.properties' -o -name 'bootstrap*.yml' \) -print0)

# JPA XML descriptors
while IFS= read -r -d '' f; do
  sed -e 's#http://xmlns\.jcp\.org/xml/ns/persistence/orm_2_[0-9]\.xsd#https://jakarta.ee/xml/ns/persistence/orm/orm_3_0.xsd#g' \
      -e 's#http://xmlns\.jcp\.org/xml/ns/persistence/persistence_2_[0-9]\.xsd#https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd#g' \
      -e 's#http://xmlns\.jcp\.org/xml/ns/persistence/orm#https://jakarta.ee/xml/ns/persistence/orm#g' \
      -e 's#http://xmlns\.jcp\.org/xml/ns/persistence#https://jakarta.ee/xml/ns/persistence#g' \
      -e 's#http://java\.sun\.com/xml/ns/persistence#https://jakarta.ee/xml/ns/persistence#g' \
      -e '/<persistence[ >]/s/version="2\.[0-9]"/version="3.0"/' \
      -e '/<entity-mappings[ >]/s/version="2\.[0-9]"/version="3.0"/' \
      -e 's/javax\.persistence\./jakarta.persistence./g' "$f" > "$TMP/out"
  apply "$f" "$TMP/out" "jpa-xml"
done < <(find "$PROJECT" -path '*/target' -prune -o -type f \( -name 'persistence.xml' -o -name 'orm.xml' \) -print0)

# ---------------------------------------------------------------- pom.xml
NEED_JAXB=0
if grep -rqs --include='*.java' --include='*.kt' 'jakarta\.xml\.bind' "$PROJECT/src" 2>/dev/null; then
  grep -q '<artifactId>jakarta.xml.bind-api</artifactId>' "$POM" || NEED_JAXB=1
fi

awk -v BOOT="$BOOT" -v JAVA="$JAVA" -v JJWT="$JJWT" -v NEED_JAXB="$NEED_JAXB" '
function tagval(s, t,   a, b) {               # first <t>value</t> in s
  a = index(s, "<" t ">"); if (a == 0) return ""
  s = substr(s, a + length(t) + 2); b = index(s, "</" t ">"); if (b == 0) return ""
  return substr(s, 1, b - 1)
}
function settag(s, t, v,   a, rest, b) {      # replace first <t>..</t> value in s
  a = index(s, "<" t ">"); if (a == 0) return s
  rest = substr(s, a + length(t) + 2); b = index(rest, "</" t ">"); if (b == 0) return s
  return substr(s, 1, a + length(t) + 1) v substr(rest, b)
}
function dropline(s, t,   n, i, arr, out, gone, first) {   # remove first line containing <t>
  n = split(s, arr, "\n"); out = ""; gone = 0; first = 1
  for (i = 1; i <= n; i++) {
    if (!gone && index(arr[i], "<" t ">")) { gone = 1; continue }
    out = first ? arr[i] : out "\n" arr[i]; first = 0
  }
  return out
}
function indentof(s) { match(s, /^[ \t]*/); return substr(s, 1, RLENGTH) }
function dep(ind, g, a, v, sc,   r) {
  r = ind "<dependency>\n" ind "    <groupId>" g "</groupId>\n" ind "    <artifactId>" a "</artifactId>\n"
  if (v != "") r = r ind "    <version>" v "</version>\n"
  if (sc != "") r = r ind "    <scope>" sc "</scope>\n"
  return r ind "</dependency>"
}
function oldjava(v) { return (v ~ /^1\.[0-9]$/ || v ~ /^([5-9]|1[0-6])$/) }
function emit(s) { if (pending != "") print pending; pending = ""; print s }
function flush_dep(b,   g, a, v, ind, ng, na) {
  g = tagval(b, "groupId"); a = tagval(b, "artifactId"); v = tagval(b, "version"); ind = indentof(b)
  if ((g == "javax.xml.bind" && a == "jaxb-api") || (g == "com.sun.xml.bind" && (a == "jaxb-impl" || a == "jaxb-core")) ||
      (g == "javax.activation" && (a == "activation" || a == "javax.activation-api"))) {
    if (pending != "") note("removed comment: " pending); pending = ""; note("removed " g ":" a); return
  }
  if (in_dm && a == "spring-boot-dependencies" && v != BOOT && v !~ /\$\{/) { note("spring-boot-dependencies " v " -> " BOOT); emit(settag(b, "version", BOOT)); return }
  if (g == "io.jsonwebtoken" && a == "jjwt") {
    note("io.jsonwebtoken:jjwt " v " -> jjwt-api/impl/jackson " JJWT)
    emit(dep(ind, g, "jjwt-api", JJWT, "") "\n" dep(ind, g, "jjwt-impl", JJWT, "runtime") "\n" dep(ind, g, "jjwt-jackson", JJWT, "runtime")); return
  }
  if (g == "io.jsonwebtoken" && a ~ /^jjwt-/ && v != "" && v != JJWT && v !~ /\$\{/) { note(a " " v " -> " JJWT); emit(settag(b, "version", JJWT)); return }
  ng = ""; na = ""
  if (g == "javax.servlet" && a == "javax.servlet-api") { ng = "jakarta.servlet"; na = "jakarta.servlet-api" }
  else if (g == "javax.validation" && a == "validation-api") { ng = "jakarta.validation"; na = "jakarta.validation-api" }
  else if (g == "javax.persistence" && (a == "javax.persistence-api" || a == "persistence-api")) { ng = "jakarta.persistence"; na = "jakarta.persistence-api" }
  else if (g == "javax.annotation" && a == "javax.annotation-api") { ng = "jakarta.annotation"; na = "jakarta.annotation-api" }
  else if (g == "javax.inject" && a == "javax.inject") { ng = "jakarta.inject"; na = "jakarta.inject-api" }
  else if (g == "javax.transaction" && (a == "javax.transaction-api" || a == "jta")) { ng = "jakarta.transaction"; na = "jakarta.transaction-api" }
  else if (g == "mysql" && a == "mysql-connector-java") { ng = "com.mysql"; na = "mysql-connector-j" }
  else if (g == "org.hibernate" && a == "hibernate-core") { ng = "org.hibernate.orm"; na = "hibernate-core" }
  if (ng != "") {
    note(g ":" a " -> " ng ":" na " (version from Boot BOM)")
    b = settag(settag(b, "groupId", ng), "artifactId", na); if (v != "") b = dropline(b, "version"); emit(b); return
  }
  if (g == "org.projectlombok" && a == "lombok" && v != "") { note("lombok: dropped explicit version " v " (Boot manages a Java 21 compatible one)"); emit(dropline(b, "version")); return }
  emit(b)
}
function flush_plugin(b,   s, t) {
  if (index(b, "<artifactId>maven-compiler-plugin</artifactId>")) {
    split("source target release", T, " ")
    for (t = 1; t <= 3; t++) { s = tagval(b, T[t]); if (oldjava(s)) { note("maven-compiler-plugin <" T[t] "> " s " -> " JAVA); b = settag(b, T[t], JAVA) } }
  }
  emit(b)
}
function flush_parent(b,   v) {
  v = tagval(b, "version")
  if (index(b, "<artifactId>spring-boot-starter-parent</artifactId>") && v != BOOT) { note("spring-boot-starter-parent " v " -> " BOOT); b = settag(b, "version", BOOT) }
  emit(b)
}
function note(m) { print "    " m > "/dev/stderr" }
BEGIN { mode = ""; buf = ""; in_dm = 0; in_build = 0; inserted = 0; pending = "" }
{
  line = $0
  if (mode != "") {
    buf = buf "\n" line
    if (index(line, "</" mode ">")) { if (mode == "dependency") flush_dep(buf); else if (mode == "plugin") flush_plugin(buf); else flush_parent(buf); mode = ""; buf = "" }
    next
  }
  if (line ~ /<dependencyManagement>/) in_dm = 1
  if (line ~ /<\/dependencyManagement>/) in_dm = 0
  if (line ~ /^[ \t]*<(dependency|plugin|parent)>/) {
    mode = line; sub(/^[ \t]*</, "", mode); sub(/>.*/, "", mode); buf = line
    if (index(line, "</" mode ">")) { if (mode == "dependency") flush_dep(buf); else if (mode == "plugin") flush_plugin(buf); else flush_parent(buf); mode = ""; buf = "" }
    next
  }
  # hold a one-line comment until we know whether the dependency it labels is removed
  if (line ~ /^[ \t]*<!--.*-->[ \t]*$/) { if (pending != "") print pending; pending = line; next }
  if (line ~ /<java\.version>/ ) { v = tagval(line, "java.version"); if (v != JAVA) { note("java.version " v " -> " JAVA); line = settag(line, "java.version", JAVA) } }
  if (line ~ /<spring-boot\.version>/) { v = tagval(line, "spring-boot.version"); if (v != BOOT) { note("spring-boot.version " v " -> " BOOT); line = settag(line, "spring-boot.version", BOOT) } }
  split("maven.compiler.source maven.compiler.target maven.compiler.release", P, " ")
  for (i = 1; i <= 3; i++) if (index(line, "<" P[i] ">")) { v = tagval(line, P[i]); if (oldjava(v)) { note(P[i] " " v " -> " JAVA); line = settag(line, P[i], JAVA) } }
  if (NEED_JAXB == 1 && !inserted && !in_dm && line ~ /^[ \t]*<\/dependencies>/ && !in_build) {
    ind = indentof(line) "    "
    emit(dep(ind, "jakarta.xml.bind", "jakarta.xml.bind-api", "", ""))
    emit(dep(ind, "org.glassfish.jaxb", "jaxb-runtime", "", "runtime"))
    note("added jakarta.xml.bind-api + org.glassfish.jaxb:jaxb-runtime (code uses jakarta.xml.bind)"); inserted = 1
  }
  if (line ~ /<build>/) in_build = 1
  if (line ~ /<\/build>/) in_build = 0
  emit(line)
}
END { if (pending != "") print pending }
' "$POM" > "$TMP/pom.out" 2> "$TMP/pom.notes"
if ! cmp -s "$POM" "$TMP/pom.out"; then
  CHANGED=$((CHANGED+1)); echo "CHANGED pom: pom.xml"; cat "$TMP/pom.notes"
  [ "$DRY" = 1 ] || cat "$TMP/pom.out" > "$POM"
fi

echo "migrate.sh: $CHANGED file(s) changed$( [ "$DRY" = 1 ] && echo ' (dry run, nothing written)')."
echo "Next: run scripts/check.sh again; remaining FINDINGS are client tasks (security DSL, RestClient, jjwt code, Hibernate code)."
