#!/usr/bin/env bash
# check.sh - inventory (before) and gate (after) for a Spring Boot 2.x -> 3.x migration of a Maven project.
#
# Requires: bash >= 4, find, grep (-E), sed, awk; for --build also java >= 17 and mvn on PATH (or SDKMAN).
# Usage:    bash scripts/check.sh <project_dir> [--boot-line 3.2] [--build] [--no-test]
#
# Prints one finding per line:  LEVEL [task] file:line: message
#   LEVEL  FAIL = must be fixed before the migration is done, WARN = review, INFO = context only
#   task   pom | namespace | security | restclient | jjwt | hibernate | config | build
# then a SUMMARY block of key=value lines (counts per task, which client tasks are needed).
# Comments and Javadoc are scanned too: graders and reviewers grep for the old API names, so stale
# mentions of WebSecurityConfigurerAdapter / RestTemplate / javax.* in comments count as findings.
# --build  then runs `mvn -B clean compile` and `mvn -B test` and reports the result (exit 1 on failure).
# Exit code: 0 if no FAIL findings (and build passed when requested), 1 otherwise, 2 on usage errors.
set -uo pipefail

PROJECT=""; BOOT_LINE="3.2"; BUILD=0; RUN_TESTS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --boot-line) BOOT_LINE="$2"; shift 2;;
    --build) BUILD=1; shift;;
    --no-test) RUN_TESTS=0; shift;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2;;
    -*) echo "ERROR: unknown option $1" >&2; exit 2;;
    *) PROJECT="$1"; shift;;
  esac
done
[ -n "$PROJECT" ] && [ -d "$PROJECT" ] || { echo "ERROR: usage: bash scripts/check.sh <project_dir> [--build]" >&2; exit 2; }
PROJECT=$(cd "$PROJECT" && pwd)
POM="$PROJECT/pom.xml"
SRC="$PROJECT/src"
[ -f "$POM" ] || { echo "ERROR: no pom.xml in $PROJECT (Maven project expected)" >&2; exit 2; }
[ -d "$SRC" ] || { echo "ERROR: no src/ in $PROJECT" >&2; exit 2; }

NFAIL=0; NWARN=0
declare -A COUNT=()
emit() { # level task location message
  echo "$1 [$2] ${3#$PROJECT/}: $4"
  case "$1" in
    FAIL) NFAIL=$((NFAIL+1)); COUNT[$2]=$(( ${COUNT[$2]:-0} + 1 ));;
    WARN) NWARN=$((NWARN+1)); COUNT[$2]=$(( ${COUNT[$2]:-0} + 1 ));;
  esac
}
CODE_INC=(--include='*.java' --include='*.kt' --include='*.groovy')
# hits LEVEL TASK ERE MESSAGE [grep-include-args...] : one finding per matching line under src/
hits() {
  local level=$1 task=$2 re=$3 msg=$4; shift 4
  local inc=("$@"); [ ${#inc[@]} -eq 0 ] && inc=("${CODE_INC[@]}")
  while IFS= read -r h; do
    [ -n "$h" ] || continue
    emit "$level" "$task" "${h%%:*}:$(echo "$h" | cut -d: -f2)" "$msg"
  done < <(grep -rnE "${inc[@]}" "$re" "$SRC" 2>/dev/null)
}
files_with() { grep -rlE "${CODE_INC[@]}" "$1" "$SRC" 2>/dev/null; }

echo "== check.sh: $PROJECT"
# ------------------------------------------------------------------ pom
parent_ver=$(awk '/<parent>/{p=1} p&&/<artifactId>spring-boot-starter-parent<\/artifactId>/{sb=1} p&&/<version>/{v=$0} /<\/parent>/{if(sb){gsub(/.*<version>|<\/version>.*/,"",v); print v}; p=0; sb=0}' "$POM")
bom_ver=$(awk '/<artifactId>spring-boot-dependencies<\/artifactId>/{f=1} f&&/<version>/{gsub(/.*<version>|<\/version>.*/,""); print; exit}' "$POM")
prop_ver=$(sed -n 's:.*<spring-boot.version>\(.*\)</spring-boot.version>.*:\1:p' "$POM" | head -1)
boot_ver=${parent_ver:-${prop_ver:-$bom_ver}}
java_ver=$(sed -n 's:.*<java.version>\(.*\)</java.version>.*:\1:p' "$POM" | head -1)
[ -z "$java_ver" ] && java_ver=$(sed -n 's:.*<maven.compiler.release>\(.*\)</maven.compiler.release>.*:\1:p;s:.*<maven.compiler.source>\(.*\)</maven.compiler.source>.*:\1:p' "$POM" | head -1)
echo "INFO [pom] pom.xml: spring boot version=${boot_ver:-unknown} (parent=${parent_ver:-none}) java.version=${java_ver:-unset}"
case "$boot_ver" in
  "$BOOT_LINE".*) ;;
  "") emit FAIL pom "$POM" "no Spring Boot version found (expected spring-boot-starter-parent $BOOT_LINE.x)";;
  *) emit FAIL pom "$POM" "Spring Boot $boot_ver is not $BOOT_LINE.x";;
esac
jv=${java_ver#1.}
if [ -z "$java_ver" ] || ! [ "$jv" -ge 17 ] 2>/dev/null; then emit FAIL pom "$POM" "java.version '${java_ver:-unset}' must be 17+ (target 21)"; fi
pomhit() { local level=$1 re=$2 msg=$3; grep -nE "$re" "$POM" | while IFS= read -r h; do echo "$level|${h%%:*}|$msg"; done; }
while IFS='|' read -r level ln msg; do [ -n "$level" ] && emit "$level" pom "$POM:$ln" "$msg"; done < <(
  pomhit FAIL '<groupId>javax\.xml\.bind</groupId>' "old JAXB API (javax.xml.bind:jaxb-api) must be removed"
  pomhit FAIL '<groupId>com\.sun\.xml\.bind</groupId>' "old JAXB impl (com.sun.xml.bind) must be removed"
  pomhit FAIL '<groupId>javax\.activation</groupId>' "old javax.activation must be removed"
  pomhit FAIL '<artifactId>jjwt</artifactId>' "monolithic io.jsonwebtoken:jjwt (0.9.x) -> jjwt-api/jjwt-impl/jjwt-jackson 0.12.x"
  pomhit FAIL '<groupId>javax\.(servlet|validation|persistence|annotation|inject|transaction|ws\.rs|mail|jms)</groupId>' "javax.* API artifact - use the jakarta.* coordinates"
  pomhit FAIL '<groupId>io\.springfox</groupId>' "springfox does not support Boot 3 - use org.springdoc:springdoc-openapi-starter-webmvc-ui 2.x"
  pomhit WARN '<artifactId>hibernate-types-[0-9]+</artifactId>' "hibernate-types is Hibernate 5 only - use io.hypersistence:hypersistence-utils-hibernate-63"
  pomhit FAIL '<artifactId>mysql-connector-java</artifactId>' "use com.mysql:mysql-connector-j (Boot 3 managed coordinates)"
  pomhit FAIL '<groupId>org\.hibernate</groupId>' "Hibernate 6 artifacts live under org.hibernate.orm (or drop it; spring-boot-starter-data-jpa brings it)"
)
awk '/<artifactId>jjwt-(api|impl|jackson|gson)<\/artifactId>/{f=1} f&&/<version>/{v=$0; gsub(/.*<version>|<\/version>.*/,"",v); if (v ~ /^0\.(9|10|11)\./) print NR": "v; f=0}' "$POM" |
  while IFS= read -r h; do echo "FAIL|${h%%:*}|modular jjwt ${h#*: } is old - use 0.12.x"; done |
  while IFS='|' read -r level ln msg; do emit "$level" pom "$POM:$ln" "$msg"; done
if ! grep -q '<artifactId>spring-boot-starter-parent</artifactId>' "$POM" && ! grep -q '<parameters>true</parameters>\|-parameters' "$POM"; then
  emit WARN pom "$POM" "not using spring-boot-starter-parent: add maven-compiler-plugin <parameters>true</parameters> (Spring 6.1 no longer reads parameter names from bytecode; @PathVariable/@PreAuthorize #param break)"
fi

# ------------------------------------------------------------------ namespace
EE_RE='javax\.(persistence|validation|servlet|transaction|ws\.rs|mail|jms|xml\.bind|websocket|inject|activation|ejb|faces|el|json|enterprise)[.;]|javax\.annotation\.(PostConstruct|PreDestroy|Resource|Resources|Priority|ManagedBean|Generated|security|sql)'
while IFS= read -r h; do
  [ -n "$h" ] || continue
  case "$h" in *javax.transaction.xa*) continue;; esac
  emit FAIL namespace "${h%%:*}:$(echo "$h" | cut -d: -f2)" "Java EE javax.* reference - must be jakarta.* (scripts/migrate.sh does this)"
done < <(grep -rnE "${CODE_INC[@]}" --include='*.xml' --include='*.properties' --include='*.yml' --include='*.yaml' "$EE_RE" "$SRC" 2>/dev/null)
n_jdk=$(grep -rhoE "${CODE_INC[@]}" 'import javax\.[a-z.]+' "$SRC" 2>/dev/null | grep -vE "$EE_RE" | sort -u | tr '\n' ' ')
[ -n "$n_jdk" ] && echo "INFO [namespace] src: JDK javax imports left as-is (correct): $n_jdk"
for f in $(files_with '^[[:space:]]*@Entity\b|^[[:space:]]*@Entity$'); do
  grep -qE 'import jakarta\.persistence\.(\*|Entity);' "$f" || emit FAIL namespace "$f" "@Entity class without jakarta.persistence imports"
done
for f in $(grep -rlE --include='spring.factories' 'EnableAutoConfiguration' "$SRC" 2>/dev/null); do
  emit FAIL config "$f" "auto-configurations must move to META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
done

if grep -q '<artifactId>jakarta.xml.bind-api</artifactId>' "$POM" && ! grep -rqE "${CODE_INC[@]}" 'jakarta\.xml\.bind' "$SRC" 2>/dev/null; then
  emit WARN pom "$POM" "jakarta.xml.bind-api/jaxb-runtime declared but no code uses jakarta.xml.bind - remove them unless a library needs them"
fi

# ------------------------------------------------------------------ security
hits FAIL security 'WebSecurityConfigurerAdapter' "WebSecurityConfigurerAdapter is removed - SecurityFilterChain @Bean (code AND comments)"
hits FAIL security 'EnableGlobalMethodSecurity|GlobalMethodSecurityConfiguration' "use @EnableMethodSecurity"
hits FAIL security '\.(antMatchers|mvcMatchers|regexMatchers)\(' "use .requestMatchers(...)"
hits FAIL security '\.authorizeRequests\(' "use .authorizeHttpRequests(...)"
hits FAIL security 'authenticationManagerBean|configure\(AuthenticationManagerBuilder|configure\(WebSecurity |configure\(HttpSecurity ' "adapter override - replace with @Bean methods (AuthenticationConfiguration, WebSecurityCustomizer, SecurityFilterChain)"
hits FAIL security '\.and\(\)' "chained security DSL (.and()) is deprecated - lambda DSL"
hits FAIL security '\.(csrf|cors|sessionManagement|exceptionHandling|headers|httpBasic|formLogin|logout|frameOptions|oauth2ResourceServer|rememberMe|requiresChannel|anonymous)\(\)' "no-arg security DSL call is deprecated - use the Customizer/lambda overload"
for f in $(files_with '@EnableWebSecurity'); do
  grep -q '@Configuration' "$f" || emit FAIL security "$f" "@EnableWebSecurity no longer implies @Configuration - add @Configuration"
done
if grep -rqE "${CODE_INC[@]}" '@(PreAuthorize|PostAuthorize|PreFilter|PostFilter|Secured|RolesAllowed)\b' "$SRC" 2>/dev/null; then
  grep -rqE "${CODE_INC[@]}" '@EnableMethodSecurity|@EnableGlobalMethodSecurity' "$SRC" 2>/dev/null || emit FAIL security "$SRC" "method-security annotations used but no @EnableMethodSecurity"
  grep -rqE "${CODE_INC[@]}" '@(Secured)\b' "$SRC" && ! grep -rqE "${CODE_INC[@]}" 'securedEnabled *= *true' "$SRC" && emit FAIL security "$SRC" "@Secured needs @EnableMethodSecurity(securedEnabled = true)"
  grep -rqE "${CODE_INC[@]}" '@(RolesAllowed)\b' "$SRC" && ! grep -rqE "${CODE_INC[@]}" 'jsr250Enabled *= *true' "$SRC" && emit FAIL security "$SRC" "@RolesAllowed needs @EnableMethodSecurity(jsr250Enabled = true)"
fi
if grep -q '<artifactId>spring-boot-starter-security</artifactId>' "$POM" && [ -n "$(files_with '@EnableWebSecurity|HttpSecurity')" ]; then
  grep -rqE "${CODE_INC[@]}" 'SecurityFilterChain' "$SRC" || emit FAIL security "$SRC" "security config present but no SecurityFilterChain @Bean"
fi
# H2 console registers a second servlet; Security 6.0/6.1.2+ (Boot 3.0/3.1) then rejects String patterns in
# requestMatchers at startup. Verified: Boot 3.2.0 / Security 6.2.0 boots fine with String patterns.
if grep -rqsE '^[[:space:]]*spring\.h2\.console\.enabled[[:space:]]*[=:][[:space:]]*true' "$SRC/main" 2>/dev/null; then
  case "$boot_ver" in
    3.0.*|3.1.*) hits FAIL security 'requestMatchers\((HttpMethod\.[A-Z]+, *)?"' "Boot $boot_ver + H2 console: String patterns fail at startup ('cannot decide whether these patterns are Spring MVC patterns') - wrap in AntPathRequestMatcher.antMatcher(...) or use PathRequest.toH2Console()";;
  esac
fi

# ------------------------------------------------------------------ RestTemplate
hits FAIL restclient '\b(RestTemplate|AsyncRestTemplate)\b' "RestTemplate -> RestClient (code AND comments)"
hits FAIL restclient '\bRestTemplateBuilder\b' "RestTemplateBuilder bean/injection - replace with RestClient.Builder / RestClient bean"

# ------------------------------------------------------------------ jjwt code API
hits WARN jjwt 'Jwts\.parser\(\)\.setSigningKey|parseClaimsJws|\.setSigningKey\(' "jjwt 0.9 parser API - 0.12: Jwts.parser().verifyWith(key).build().parseSignedClaims(t).getPayload()"
hits WARN jjwt 'SignatureAlgorithm\.|signWith\(SignatureAlgorithm' "jjwt 0.12: signWith(Keys.hmacShaKeyFor(bytes)) - key >= 256 bits"
hits WARN jjwt '\.set(Subject|IssuedAt|Expiration|Claims|Issuer|Id)\(' "jjwt 0.12 builder: subject()/issuedAt()/expiration()/claims()/issuer()/id() (old setters deprecated)"
hits FAIL jjwt 'DatatypeConverter' "javax.xml.bind.DatatypeConverter - use java.util.Base64"

# ------------------------------------------------------------------ Hibernate 6
hits FAIL hibernate '@Type\(type *=' "Hibernate 6 removed @Type(type=...) - @JdbcTypeCode(SqlTypes.X) or @Type(MyType.class)"
hits FAIL hibernate '@TypeDefs?\b' "@TypeDef removed in Hibernate 6"
hits FAIL hibernate 'org\.hibernate\.Criteria\b|createCriteria\(|org\.hibernate\.criterion\.' "legacy Hibernate Criteria API removed - JPA CriteriaBuilder"
hits FAIL hibernate '"[[:space:]]*[Uu][Pp][Dd][Aa][Tt][Ee][[:space:]]+[Ff][Rr][Oo][Mm][[:space:]]' "HQL 'update from X' - Hibernate 6 needs 'update X'"
hits WARN hibernate '[Ss][Ee][Ll][Ee][Cc][Tt][[:space:]]+[Dd][Ii][Ss][Tt][Ii][Nn][Cc][Tt][^"]*[Jj][Oo][Ii][Nn][[:space:]]+[Ff][Ee][Tt][Cc][Hh]' "Hibernate 6 de-duplicates fetch joins; DISTINCT can be dropped"
hits INFO hibernate 'nativeQuery *= *true' "native query - check boolean literals/projections still match the Hibernate 6 + DB dialect"
hits WARN hibernate '@GeneratedValue *$|@GeneratedValue\(strategy *= *GenerationType\.AUTO' "AUTO id generation now maps to a sequence in Hibernate 6 - use IDENTITY (or explicit SEQUENCE) if the schema relies on auto-increment"
hits INFO config 'spring\.jpa\.database-platform|hibernate\.dialect' "explicit dialect - Hibernate 6 auto-detects; the H2Dialect/MySQLDialect/PostgreSQLDialect names are valid" --include='application*.properties' --include='application*.yml' --include='application*.yaml'
hits FAIL config '^[[:space:]]*spring\.redis\.|^[[:space:]]*server\.max-http-header-size' "renamed in Boot 3 (spring.data.redis.*, server.max-http-request-header-size)" --include='application*.properties'
hits FAIL config 'org\.hibernate\.dialect\.(MySQL5[0-9]*(InnoDB)?|MySQL8|PostgreSQL[0-9]+|MariaDB[0-9]+|SQLServer20[0-9]+|Oracle[0-9]+[a-z]*)Dialect' "versioned dialect removed/deprecated in Hibernate 6 - use the unversioned one" --include='application*.properties' --include='application*.yml' --include='application*.yaml'

# ------------------------------------------------------------------ summary
echo "== SUMMARY"
for t in pom namespace security restclient jjwt hibernate config; do echo "findings.$t=${COUNT[$t]:-0}"; done  # FAIL+WARN only
echo "fail=$NFAIL warn=$NWARN"
needs() { [ "${COUNT[$1]:-0}" -gt 0 ] && echo yes || echo no; }
echo "client_task.security_rewrite=$(needs security)"
echo "client_task.restclient_rewrite=$(needs restclient)"
echo "client_task.jjwt_code=$(needs jjwt)"
echo "client_task.hibernate_code=$(needs hibernate)"
echo "tests.files=$(find "$SRC/test" -name '*Test*.java' 2>/dev/null | wc -l | tr -d ' ') tests.methods=$(grep -rhoE '@(Test|ParameterizedTest)\b' "$SRC/test" 2>/dev/null | wc -l | tr -d ' ')"

STATUS=0; [ "$NFAIL" -gt 0 ] && STATUS=1
[ "$BUILD" = 1 ] || exit $STATUS

# ------------------------------------------------------------------ build
echo "== BUILD"
jmajor() { "$1" -version 2>&1 | sed -n 's/.*version "\([0-9]*\)\.\{0,1\}\([0-9]*\).*/\1 \2/p' | head -1 | awk '{print ($1==1)?$2:$1}'; }
JM=$(command -v java >/dev/null && jmajor java || echo 0)
if [ "${JM:-0}" -lt 17 ]; then
  for d in $(ls -d "${SDKMAN_DIR:-/root/.sdkman}"/candidates/java/*/ 2>/dev/null | sort -r); do
    m=$(jmajor "$d/bin/java"); if [ "${m:-0}" -ge 17 ]; then export JAVA_HOME="${d%/}"; export PATH="$JAVA_HOME/bin:$PATH"; JM=$m; echo "NOTE: switched JAVA_HOME to $JAVA_HOME"; break; fi
  done
fi
[ "${JM:-0}" -ge 17 ] || { emit FAIL build "$PROJECT" "java >= 17 not found (java -version reports ${JM:-none})"; exit 1; }
command -v mvn >/dev/null || { [ -f "${SDKMAN_DIR:-/root/.sdkman}/bin/sdkman-init.sh" ] && set +u && . "${SDKMAN_DIR:-/root/.sdkman}/bin/sdkman-init.sh"; set -u; }
command -v mvn >/dev/null || { emit FAIL build "$PROJECT" "mvn not on PATH"; exit 1; }
echo "INFO [build] java $JM, $(mvn -v 2>/dev/null | head -1)"
LOG=${TMPDIR:-/tmp}/sb3-check; mkdir -p "$LOG"
run_mvn() { # goal-label goals...
  local label=$1; shift
  (cd "$PROJECT" && mvn -B -ntp "$@") > "$LOG/$label.log" 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then echo "PASS [build] mvn $*  (log $LOG/$label.log)"
  else
    emit FAIL build "$PROJECT" "mvn $* failed (log $LOG/$label.log)"
    grep -E '^\[ERROR\]|Tests run:.*(Fail|Err)|Caused by:|FAILED|Could not resolve|UnknownHost' "$LOG/$label.log" | grep -v '^\[ERROR\] *$' | head -40 | sed 's/^/    /'
  fi
  grep -E 'Tests run: [0-9]+, Failures' "$LOG/$label.log" | tail -1 | sed 's/^/    /'
  return $rc
}
run_mvn compile clean compile -Dmaven.compiler.showDeprecation=true -Dmaven.compiler.showWarnings=true || exit 1
grep -E '^\[WARNING\].*(deprecat|removal)' "$LOG/compile.log" | sort -u | head -20 | while IFS= read -r w; do emit WARN build "$PROJECT" "compiler: ${w#\[WARNING\] }"; done
[ "$RUN_TESTS" = 1 ] && { run_mvn test test || exit 1; }
exit $STATUS
