#!/usr/bin/env bash
# Spring Boot 2.x -> 3.2.x migration helper.
#
#   bash migrate.sh apply    mechanical, idempotent rewrites + inventory of what is left for hand edits
#   bash migrate.sh verify   `mvn clean compile`, `mvn test`, and residual legacy-pattern checks
#
# Reads one JSON object on stdin ({"state": {"workspace": "<project root>"}, ...}) and writes one
# JSON object to stdout. Needs only bash, perl (core, no modules), grep, find, cksum; verify also
# needs java and mvn. MAVEN_ARGS (Maven 3.9+) is honoured, e.g. -Dmaven.repo.local=...
# Works with GNU and BSD userlands (no sed -i, no bash 4 features).

set -u

TARGET_BOOT="${TARGET_BOOT:-3.2.0}"   # spring-boot-starter-parent target (3.2.x)
TARGET_JAVA="${TARGET_JAVA:-21}"      # java.version target
TARGET_JJWT="${TARGET_JJWT:-0.12.3}"  # modular jjwt-api/impl/jackson
export TARGET_BOOT TARGET_JAVA TARGET_JJWT

die() { echo "migrate.sh: $*" >&2; exit 1; }

MODE="${1:-}"
case "$MODE" in apply|verify) ;; *) die "usage: bash migrate.sh apply|verify  (JSON on stdin)";; esac

INPUT="$(cat)"
WS="$(printf '%s' "$INPUT" | perl -0ne 'if (/"workspace"\s*:\s*"((?:[^"\\]|\\.)*)"/) { $v=$1; $v =~ s/\\\//\//g; $v =~ s/\\\\/\\/g; print $v }')"
[ -n "$WS" ] || die "state.workspace (path to the Maven project root) is missing from the stdin JSON"
[ -d "$WS" ] || die "workspace '$WS' is not a directory"
WS="$(cd "$WS" && pwd)"
[ -f "$WS/pom.xml" ] || die "no pom.xml in '$WS' - this helper only handles Maven projects"

# ---------------------------------------------------------------- JSON helpers
jesc() { perl -0pe 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r/\\r/g; s/\n/\\n/g; s/([\x00-\x1f])/sprintf("\\u%04x",ord($1))/ge'; }
jstr() { printf '"%s"' "$(printf '%s' "$1" | jesc)"; }
# newline-separated text on stdin -> JSON array of strings (blank lines dropped)
jlist() { perl -ne 'chomp; next unless length; s/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r//g; s/([\x00-\x1f])/sprintf("\\u%04x",ord($1))/ge; push @a, "\"$_\""; END { print "[", join(",", @a), "]" }'; }
jbool() { if [ -n "$1" ]; then printf true; else printf false; fi; }

# ---------------------------------------------------------------- file helpers
EXCL="--exclude-dir=target --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.mvn --exclude-dir=build"
java_files() { find "$WS" -type f -name '*.java' -not -path '*/target/*' -not -path '*/.git/*' -not -path '*/node_modules/*'; }
pom_files()  { find "$WS" -type f -name 'pom.xml' -not -path '*/target/*' -not -path '*/.git/*' -not -path '*/node_modules/*'; }
res_files()  { find "$WS" -type f \( -name '*.properties' -o -name '*.yml' -o -name '*.yaml' -o -name '*.xml' \) -path '*/src/*' -not -path '*/target/*' -not -path '*/.git/*'; }
rel() { printf '%s' "${1#$WS/}"; }

# grep java sources: prints "path:line: code" (relative, trimmed, max 200 chars)
gj() {
  (cd "$WS" && grep -rnE $EXCL --include='*.java' -- "$1" . 2>/dev/null) \
    | perl -ne 's{^\./}{}; s/^([^:]+:\d+:)\s*/$1 /; s/\s+$//; $_ = substr($_,0,200); print "$_\n"'
}
# same, restricted to files whose content matches $2 (e.g. Spring Security config classes)
gj_in() {
  local pat="$1" filt="$2" f
  (cd "$WS" && grep -rlE $EXCL --include='*.java' -- "$filt" . 2>/dev/null) | while read -r f; do
    grep -nE -- "$pat" "$WS/$f" 2>/dev/null | perl -sne 's/^(\d+):\s*/$f:$1: /; s/\s+$//; $_ = substr($_,0,200); print "$_\n"' -- -f="${f#./}"
  done
}

# Jakarta EE packages that moved javax -> jakarta. JDK packages (javax.sql, javax.crypto, javax.net,
# javax.naming, javax.management, javax.security.auth, javax.xml.parsers/transform/stream,
# javax.transaction.xa, javax.annotation.processing, ...) are NOT in this list and must stay javax.
EE_RE='javax\.((?:persistence|validation|servlet|transaction\b(?!\.xa)|ws\.rs|mail|jms|xml\.bind|inject|websocket|faces|ejb|enterprise|json|batch|el|activation)\b|annotation\.(?:PostConstruct|PreDestroy|Resource|Resources|ManagedBean|Priority|security)\b)'
EE_GREP='javax\.(persistence|validation|servlet|ws\.rs|mail|jms|xml\.bind|inject|websocket|faces|ejb|enterprise|json|batch|activation)\b|javax\.transaction\.[A-Z]|javax\.transaction\.(Transactional|UserTransaction)|javax\.annotation\.(PostConstruct|PreDestroy|Resource|Resources|ManagedBean|Priority|security)\b|javax\.el\.'

CHANGES=""
note() { CHANGES="${CHANGES}$1"$'\n'; }
# edit FILE "description" 'perl -0 code'   (records the description only if the file changed)
edit() {
  local f="$1" desc="$2" code="$3" before after
  before="$(cksum < "$f")"
  perl -0pi -e "$code" "$f" || die "perl edit failed on $f ($desc)"
  after="$(cksum < "$f")"
  [ "$before" != "$after" ] && note "$(rel "$f"): $desc"
  return 0
}

# perl snippet: remove a <dependency> block with the given groupId/artifactId (+ a JAXB/Java-8 comment just above it)
rm_dep() {
  local g="$1" a="$2"
  printf '%s' 's{(?:^[ \t]*<!--[^\n]*?(?i:jaxb|java\s*(?:1\.)?(?:8|9|11)|activation|xml\.?bind)[^\n]*?-->[ \t]*\n)?^[ \t]*<dependency>(?:(?!</dependency>).)*?<groupId>\s*'"$g"'\s*</groupId>\s*<artifactId>\s*'"$a"'\s*</artifactId>(?:(?!</dependency>).)*</dependency>[ \t]*\n}{}gms; s/\n([ \t]*\n){2,}/\n\n/g;'
}
# perl snippet: re-coordinate a dependency and drop its explicit <version> (Spring Boot 3 manages it)
recoord_dep() {
  local g="$1" a="$2" ng="$3" na="$4"
  printf '%s' 's{(<dependency>(?:(?!</dependency>).)*?<groupId>)\s*'"$g"'\s*(</groupId>\s*<artifactId>)\s*'"$a"'\s*(</artifactId>)((?:(?!</dependency>).)*</dependency>)}{ my ($p,$m,$e,$r)=($1,$2,$3,$4); $r =~ s/\n?[ \t]*<version>[^<]*<\/version>//; "${p}'"$ng"'${m}'"$na"'${e}${r}" }gse;'
}

# ================================================================== apply
apply() {
  local root="$WS/pom.xml" p f

  # --- baseline (before any edit)
  local boot_before java_before
  boot_before="$(perl -0ne 'print $1 if m{<parent>(?:(?!</parent>).)*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>(?:(?!</parent>).)*?<version>\s*([^<\s]+)\s*</version>}s' "$root")"
  [ -n "$boot_before" ] || boot_before="$(perl -0ne 'print $1 if m{<spring-boot\.version>\s*([^<\s]+)\s*</spring-boot\.version>}' "$root")"
  java_before="$(perl -0ne 'print $1 if m{<java\.version>\s*([^<\s]+)\s*</java\.version>}' "$root")"

  # --- 1. pom.xml: Boot version, Java version, removed/renamed dependencies
  for p in $(pom_files); do
    edit "$p" "spring-boot-starter-parent -> $TARGET_BOOT" \
      's{(<parent>(?:(?!</parent>).)*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>(?:(?!</parent>).)*?<version>)\s*2\.[^<]*(</version>)}{$1$ENV{TARGET_BOOT}$2}s'
    edit "$p" "spring-boot.version property / spring-boot-dependencies BOM -> $TARGET_BOOT" \
      's{<spring-boot\.version>\s*2\.[^<]*</spring-boot\.version>}{<spring-boot.version>$ENV{TARGET_BOOT}</spring-boot.version>}g; s{(<artifactId>\s*spring-boot-dependencies\s*</artifactId>\s*<version>)\s*2\.[^<]*(</version>)}{$1$ENV{TARGET_BOOT}$2}g'
    edit "$p" "Java version -> $TARGET_JAVA (java.version / maven.compiler.* / compiler plugin source,target,release)" \
      's{<(java\.version|maven\.compiler\.(?:source|target|release))>\s*(?:1\.[5-8]|[5-9]|1[0-6])\s*</\1>}{<$1>$ENV{TARGET_JAVA}</$1>}g; s{<(source|target|release)>\s*(?:1\.[5-8]|[5-9]|1[0-6])\s*</\1>}{<$1>$ENV{TARGET_JAVA}</$1>}g'
    edit "$p" "removed javax.xml.bind:jaxb-api (conflicts with Jakarta EE)" "$(rm_dep 'javax\.xml\.bind' 'jaxb-api')"
    edit "$p" "removed com.sun.xml.bind:jaxb-impl" "$(rm_dep 'com\.sun\.xml\.bind' 'jaxb-impl')"
    edit "$p" "removed com.sun.xml.bind:jaxb-core" "$(rm_dep 'com\.sun\.xml\.bind' 'jaxb-core')"
    edit "$p" "removed javax.activation:activation" "$(rm_dep 'javax\.activation' 'activation')"
    edit "$p" "removed javax.activation:javax.activation-api" "$(rm_dep 'javax\.activation' 'javax\.activation-api')"
    edit "$p" "removed com.sun.activation:javax.activation" "$(rm_dep 'com\.sun\.activation' 'javax\.activation')"
    edit "$p" "removed org.hibernate:hibernate-entitymanager (merged into hibernate-core 6)" "$(rm_dep 'org\.hibernate' 'hibernate-entitymanager')"
    edit "$p" "javax.servlet-api -> jakarta.servlet:jakarta.servlet-api (Boot-managed version)" "$(recoord_dep 'javax\.servlet' 'javax\.servlet-api' 'jakarta.servlet' 'jakarta.servlet-api')"
    edit "$p" "validation-api -> jakarta.validation:jakarta.validation-api" "$(recoord_dep 'javax\.validation' 'validation-api' 'jakarta.validation' 'jakarta.validation-api')"
    edit "$p" "javax.persistence-api -> jakarta.persistence:jakarta.persistence-api" "$(recoord_dep 'javax\.persistence' 'javax\.persistence-api' 'jakarta.persistence' 'jakarta.persistence-api')"
    edit "$p" "javax.annotation-api -> jakarta.annotation:jakarta.annotation-api" "$(recoord_dep 'javax\.annotation' 'javax\.annotation-api' 'jakarta.annotation' 'jakarta.annotation-api')"
    edit "$p" "javax.transaction-api -> jakarta.transaction:jakarta.transaction-api" "$(recoord_dep 'javax\.transaction' 'javax\.transaction-api' 'jakarta.transaction' 'jakarta.transaction-api')"
    edit "$p" "org.hibernate:hibernate-core -> org.hibernate.orm:hibernate-core (Boot-managed 6.x)" "$(recoord_dep 'org\.hibernate' 'hibernate-core' 'org.hibernate.orm' 'hibernate-core')"
    # monolithic jjwt 0.9.x -> modular jjwt 0.12.x (api + runtime impl + runtime jackson)
    edit "$p" "io.jsonwebtoken:jjwt -> jjwt-api/jjwt-impl/jjwt-jackson $TARGET_JJWT" \
      's{^([ \t]*)<dependency>(?:(?!</dependency>).)*?<groupId>\s*io\.jsonwebtoken\s*</groupId>\s*<artifactId>\s*jjwt\s*</artifactId>(?:(?!</dependency>).)*</dependency>}{ my $i=$1; my $j="$i    "; my $v=$ENV{TARGET_JJWT}; join("\n", map { my ($a,$s)=@$_; "$i<dependency>\n$j<groupId>io.jsonwebtoken</groupId>\n$j<artifactId>$a</artifactId>\n$j<version>$v</version>\n".($s ? "$j<scope>runtime</scope>\n" : "")."$i</dependency>" } (["jjwt-api",0],["jjwt-impl",1],["jjwt-jackson",1])) }gmse'
    # Lombok older than 1.18.30 does not run on JDK 21: let Boot 3.2 manage it
    edit "$p" "lombok: dropped explicit pre-1.18.30 version (Boot-managed version supports JDK 21)" \
      's{(<artifactId>\s*lombok\s*</artifactId>)(\s*<version>\s*1\.(?:1[0-7]|18\.(?:[0-9]|[12][0-9]))(?:\.[^<]*)?\s*</version>)}{$1}g'
  done

  # java.version property must exist for the root pom on the Boot parent (Boot 3 defaults to 17)
  if grep -q 'spring-boot-starter-parent' "$root" && ! grep -q '<java.version>' "$root"; then
    edit "$root" "added <java.version>$TARGET_JAVA</java.version>" \
      'if (m{<properties>}) { s{<properties>}{<properties>\n        <java.version>$ENV{TARGET_JAVA}</java.version>}; } else { s{(</parent>)}{$1\n\n    <properties>\n        <java.version>$ENV{TARGET_JAVA}</java.version>\n    </properties>}; }'
  fi

  # --- 2. Java sources (main and test): javax -> jakarta, Security 6 renames, Hibernate 6 HQL
  for f in $(java_files); do
    edit "$f" "javax.* (Jakarta EE) -> jakarta.*" 's/\b'"$EE_RE"'/jakarta.$1/g'
    edit "$f" "@EnableGlobalMethodSecurity -> @EnableMethodSecurity" 's/\bEnableGlobalMethodSecurity\b/EnableMethodSecurity/g'
    edit "$f" "antMatchers/mvcMatchers( -> requestMatchers(" 's/\.(?:antMatchers|mvcMatchers)\(/.requestMatchers(/g'
    edit "$f" "authorizeRequests( -> authorizeHttpRequests(" 's/\.authorizeRequests\(/.authorizeHttpRequests(/g'
    edit "$f" "HQL 'update from X' -> 'update X'" 's/("\s*)(update)\s+from\s+/$1$2 /gi'
  done

  # --- 3. resources: renamed Hibernate dialects, javax.persistence.* property keys, persistence.xml namespace
  for f in $(res_files); do
    edit "$f" "Hibernate 6 dialect names (versioned dialects -> MySQLDialect/PostgreSQLDialect/OracleDialect/SQLServerDialect/MariaDBDialect)" \
      's/org\.hibernate\.dialect\.MySQL(?:5|55|57|8)(?:InnoDB)?Dialect\b/org.hibernate.dialect.MySQLDialect/g; s/org\.hibernate\.dialect\.MySQLInnoDBDialect\b/org.hibernate.dialect.MySQLDialect/g; s/org\.hibernate\.dialect\.PostgreSQL\d+Dialect\b/org.hibernate.dialect.PostgreSQLDialect/g; s/org\.hibernate\.dialect\.Oracle\d+[cgi]?Dialect\b/org.hibernate.dialect.OracleDialect/g; s/org\.hibernate\.dialect\.SQLServer\d+Dialect\b/org.hibernate.dialect.SQLServerDialect/g; s/org\.hibernate\.dialect\.MariaDB\d+Dialect\b/org.hibernate.dialect.MariaDBDialect/g'
    edit "$f" "javax.persistence.* keys -> jakarta.persistence.*" 's/\bjavax\.persistence\./jakarta.persistence./g'
    case "$f" in *.xml)
      edit "$f" "persistence/orm xml namespace -> https://jakarta.ee/xml/ns/persistence (3.0)" \
        's{https?://(?:xmlns\.jcp\.org|java\.sun\.com)/xml/ns/persistence(/orm)?}{https://jakarta.ee/xml/ns/persistence$1}g; s{(orm|persistence)_2_[0-2]\.xsd}{$1_3_0.xsd}g; s{(<(?:persistence|entity-mappings)\b[^>]*\bversion=")2\.[0-2]"}{${1}3.0"}g'
    ;; esac
  done

  # --- 4. if code still needs XML binding, add the Jakarta artifacts (Boot-managed versions)
  if [ -n "$(gj 'import jakarta\.xml\.bind')" ] && ! grep -q 'jakarta.xml.bind-api' "$root"; then
    edit "$root" "added jakarta.xml.bind-api + org.glassfish.jaxb:jaxb-runtime (code uses jakarta.xml.bind)" \
      'my ($pre,$post) = m{^(.*?)(<build>.*)\z}s ? ($1,$2) : ($_,""); $pre =~ s{(.*)(\n[ \t]*</dependencies>)}{$1\n        <dependency>\n            <groupId>jakarta.xml.bind</groupId>\n            <artifactId>jakarta.xml.bind-api</artifactId>\n        </dependency>\n        <dependency>\n            <groupId>org.glassfish.jaxb</groupId>\n            <artifactId>jaxb-runtime</artifactId>\n        </dependency>$2}s; $_ = $pre.$post;'
  fi

  # ---------------------------------------------------------------- inventory of what is left
  local SEC_FILTER='org\.springframework\.security\.config|HttpSecurity|WebSecurity'
  local sec rest legacy review
  sec="$( {
    gj 'WebSecurityConfigurerAdapter|GlobalMethodSecurityConfiguration|authenticationManagerBean\(|configure\(\s*(AuthenticationManagerBuilder|WebSecurity|HttpSecurity)\b'
    gj_in '\.and\(\)|\.(csrf|cors|sessionManagement|exceptionHandling|headers|httpBasic|formLogin|logout|rememberMe|oauth2Login|oauth2ResourceServer|authorizeHttpRequests|requestCache|securityContext|anonymous)\(\)' "$SEC_FILTER"
    gj '\.regexMatchers\(|\.antMatcher\(|\.ignoring\(\)\.(antMatchers|requestMatchers)'
    (cd "$WS" && grep -rlE $EXCL --include='*.java' -- '@EnableWebSecurity' . 2>/dev/null) | while read -r f; do
      grep -q '@Configuration' "$WS/$f" || echo "${f#./}: @EnableWebSecurity without @Configuration (Security 6 no longer meta-annotates @Configuration)"
    done
    if [ -n "$(gj '@(PreAuthorize|PostAuthorize|PreFilter|PostFilter|Secured|RolesAllowed)\b')" ] && [ -z "$(gj '@EnableMethodSecurity')" ]; then
      echo "method-security annotations are used but no class has @EnableMethodSecurity"
    fi
  } | sort -u )"

  rest="$( { gj '\bRestTemplate\b|\bRestTemplateBuilder\b|\bAsyncRestTemplate\b' ; } | sort -u )"

  legacy="$( {
    gj 'org\.hibernate\.Criteria\b|createCriteria\(|org\.hibernate\.criterion\.|@TypeDefs?\b|\bType\(\s*type\s*=|org\.hibernate\.type\.[A-Za-z]+Type\b|StandardBasicTypes|createSQLQuery\(|setResultTransformer|Transformers\.aliasToBean|@GenericGenerator|org\.hibernate\.annotations\.Where\b'
    gj '"\s*(update|UPDATE)\s+from\s+'
    gj 'GenerationType\.AUTO|@GeneratedValue\s*(\(\s*\))?\s*$' | sed 's/$/ (Hibernate 6 AUTO now uses a per-entity <entity>_seq sequence, allocationSize 50; use IDENTITY or an explicit @SequenceGenerator to match the existing schema)/'
    gj_in 'Jwts\.parser\(\)|parseClaimsJws|parseClaimsJwt|setSigningKey|SignatureAlgorithm|TextCodec|DatatypeConverter|\.setSubject\(|\.setExpiration\(|\.setIssuedAt\(|\.setClaims\(' 'io\.jsonwebtoken'
    gj 'WebMvcConfigurerAdapter|HandlerInterceptorAdapter|getStatusCodeValue\(\)|getRawStatusCode\(\)|org\.springframework\.boot\.context\.properties\.ConstructorBinding|ErrorController.*getErrorPath|import javax\.annotation\.\*;|import javax\.transaction\.\*;'
    (cd "$WS" && grep -rnE $EXCL --include='*.java' -- "$EE_GREP" . 2>/dev/null) | perl -ne 's{^\./}{}; s/\s+$//; print substr($_,0,200)."\n"'
    (cd "$WS" && grep -rnE $EXCL --include='*.properties' --include='*.yml' --include='*.yaml' -- 'hibernate\.id\.new_generator_mappings|org\.hibernate\.dialect\.(MySQL|PostgreSQL|Oracle|SQLServer|MariaDB|DB2|Sybase)[0-9]+[A-Za-z]*Dialect' . 2>/dev/null) | perl -ne 's{^\./}{}; s/\s+$//; print "$_\n"'
    (cd "$WS" && find . -path '*/META-INF/spring.factories' -not -path '*/target/*' 2>/dev/null) | while read -r f; do
      grep -q 'EnableAutoConfiguration' "$WS/$f" && echo "${f#./}: auto-configurations must move to META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
    done
  } | sort -u )"

  review="$( for p in $(pom_files); do
    perl -0ne '
      my $f = $ARGV; $f =~ s{^\Q$ENV{WS}\E/}{};
      while (m{<dependency>((?:(?!</dependency>).)*)</dependency>}gs) {
        my $b = $1; my ($g) = $b =~ m{<groupId>\s*([^<\s]+)}; my ($a) = $b =~ m{<artifactId>\s*([^<\s]+)}; my ($v) = $b =~ m{<version>\s*([^<\s]+)};
        next unless $g && $a;
        print "$f: $g:$a is not Spring Boot 3 compatible (use springdoc-openapi-starter-webmvc-ui 2.x)\n" if $g =~ /springfox/ || $a eq "springdoc-openapi-ui";
        print "$f: $g:$a still uses the javax namespace - find its Jakarta replacement\n" if $g =~ /^javax\./;
        print "$f: $g:$a pins version $v - Spring Boot 3.2 manages it; remove the <version> or check compatibility\n" if defined $v && $g =~ /^org\.springframework(\.|$)/ && $v !~ /^\$/;
        print "$f: $g:$a $v - jjwt below 0.12 has a different API; align with $ENV{TARGET_JJWT}\n" if $g eq "io.jsonwebtoken" && defined $v && $v =~ /^0\.(?:[0-9]|1[01])\./;
        print "$f: $g:$a $v - Spring Cloud must be 2023.0.x for Boot 3.2\n" if $a eq "spring-cloud-dependencies" && defined $v && $v !~ /^2023\./;
      }' "$p"
  done | sort -u )"

  local boot_after java_after
  boot_after="$(perl -0ne 'print $1 if m{<parent>(?:(?!</parent>).)*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>(?:(?!</parent>).)*?<version>\s*([^<\s]+)\s*</version>}s' "$root")"
  java_after="$(perl -0ne 'print $1 if m{<java\.version>\s*([^<\s]+)\s*</java\.version>}' "$root")"

  printf '{'
  printf '"baseline":{"spring_boot_before":%s,"java_version_before":%s,"spring_boot_after":%s,"java_version_after":%s,"java_files":%s},' \
    "$(jstr "$boot_before")" "$(jstr "$java_before")" "$(jstr "$boot_after")" "$(jstr "$java_after")" "$(java_files | wc -l | tr -d ' ')"
  printf '"mechanical_changes":%s,' "$(printf '%s' "$CHANGES" | jlist)"
  printf '"security_findings":%s,' "$(printf '%s' "$sec" | jlist)"
  printf '"rest_template_findings":%s,' "$(printf '%s' "$rest" | jlist)"
  printf '"legacy_api_findings":%s,' "$(printf '%s' "$legacy" | jlist)"
  printf '"pom_review":%s,' "$(printf '%s' "$review" | jlist)"
  printf '"needs_security_rewrite":%s,' "$(jbool "$sec")"
  printf '"uses_rest_template":%s,' "$(jbool "$rest")"
  printf '"needs_legacy_api_rewrite":%s' "$(jbool "$legacy$review")"
  printf '}\n'
}

# ================================================================== verify
verify() {
  command -v mvn >/dev/null 2>&1 || die "mvn not on PATH (in the task container: source /root/.sdkman/bin/sdkman-init.sh)"
  command -v java >/dev/null 2>&1 || die "java not on PATH"
  local logs root="$WS/pom.xml" issues="" jv jmajor mv
  logs="$(mktemp -d "${TMPDIR:-/tmp}/boot3-verify.XXXXXX")"
  jv="$(java -version 2>&1 | head -1)"
  jmajor="$(printf '%s' "$jv" | perl -ne 'if (/version "(\d+)(?:\.(\d+))?/) { print $1 == 1 ? $2 : $1 }')"
  mv="$(mvn -v 2>/dev/null | head -1)"
  add() { issues="${issues}$1"$'\n'; }

  [ -n "$jmajor" ] && [ "$jmajor" -lt 17 ] && add "JDK on PATH is $jv; Spring Boot 3 needs 17+ and this migration targets $TARGET_JAVA (sdk use java 21.x / set JAVA_HOME)"

  (cd "$WS" && mvn -B -ntp clean compile > "$logs/compile.log" 2>&1); local ce=$?
  local te=-1
  if [ $ce -eq 0 ]; then (cd "$WS" && mvn -B -ntp test > "$logs/test.log" 2>&1); te=$?; else : > "$logs/test.log"; fi

  # residual legacy patterns (each is a migration gap even when the build is green)
  local bootv javav
  bootv="$(perl -0ne 'print $1 if m{<parent>(?:(?!</parent>).)*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>(?:(?!</parent>).)*?<version>\s*([^<\s]+)\s*</version>}s' "$root")"
  javav="$(perl -0ne 'print $1 if m{<java\.version>\s*([^<\s]+)\s*</java\.version>}' "$root")"
  if grep -q spring-boot-starter-parent "$root"; then
    case "$bootv" in 3.2.*) ;; *) add "pom.xml: spring-boot-starter-parent is '$bootv', expected 3.2.x";; esac
  fi
  [ -n "$javav" ] && [ "$javav" != "$TARGET_JAVA" ] && add "pom.xml: java.version is '$javav', expected $TARGET_JAVA"
  for p in $(pom_files); do
    grep -nE 'javax\.xml\.bind|<artifactId>\s*jaxb-api\s*</artifactId>' "$p" | sed "s|^|$(rel "$p"):|; s|\$| (old JAXB must be removed)|"
    grep -nE '<artifactId>\s*jjwt\s*</artifactId>|<version>\s*0\.9\.[0-9]+\s*</version>' "$p" | sed "s|^|$(rel "$p"):|; s|\$| (old monolithic jjwt)|"
  done > "$logs/pom-residuals.txt"
  [ -s "$logs/pom-residuals.txt" ] && issues="${issues}$(cat "$logs/pom-residuals.txt")"$'\n'
  local r
  r="$(cd "$WS" && grep -rnE $EXCL --include='*.java' -- "$EE_GREP" . 2>/dev/null | sed 's|^\./||')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (javax EE namespace left)|')"
  r="$(gj 'WebSecurityConfigurerAdapter|@EnableGlobalMethodSecurity|EnableGlobalMethodSecurity|\.antMatchers\(|\.mvcMatchers\(|\.authorizeRequests\(|authenticationManagerBean\(')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (removed Spring Security 5 API)|')"
  r="$(gj_in '\.and\(\)|\.(csrf|cors|sessionManagement|exceptionHandling|headers|httpBasic|formLogin|logout|authorizeHttpRequests)\(\)' 'org\.springframework\.security\.config|HttpSecurity')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (chained security DSL - use lambda DSL)|')"
  r="$(gj '\bRestTemplate\b|\bAsyncRestTemplate\b')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (RestTemplate - migrate to RestClient)|')"
  r="$(gj '"\s*(update|UPDATE)\s+from\s+')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (HQL update from)|')"
  r="$(gj 'org\.hibernate\.Criteria\b|createCriteria\(|@TypeDef\b|\bType\(\s*type\s*=')"; [ -n "$r" ] && add "$(printf '%s' "$r" | sed 's|$| (removed Hibernate 5 API)|')"
  if [ -n "$(gj '@(PreAuthorize|PostAuthorize|PreFilter|PostFilter|Secured)\b')" ] && [ -z "$(gj '@EnableMethodSecurity')" ]; then add "method-security annotations used but @EnableMethodSecurity is missing"; fi
  if [ -n "$(gj '^\s*@Entity\b')" ] && [ -z "$(gj 'import jakarta\.persistence')" ]; then add "@Entity classes exist but nothing imports jakarta.persistence"; fi
  (cd "$WS" && grep -rlE $EXCL --include='*.java' -- '@EnableWebSecurity' . 2>/dev/null) | while read -r f; do
    grep -q '@Configuration' "$WS/$f" || echo "${f#./}: @EnableWebSecurity without @Configuration"
  done > "$logs/cfg.txt"
  [ -s "$logs/cfg.txt" ] && issues="${issues}$(cat "$logs/cfg.txt")"$'\n'

  local cerr terr tsum
  # keep real diagnostics, drop Maven boilerplate; paths relative to the workspace; de-duplicated
  local NOISE='Re-run Maven|re-run Maven|-> \[Help|\[Help [0-9]+\] http|full stack trace|For more information about the errors|^\[ERROR\] *$'
  cerr="$(grep -E '^\[ERROR\]' "$logs/compile.log" | grep -vE "$NOISE" | perl -sne 's/\Q$ws\E\///g; s/\s+$//; print "$_\n" unless $seen{$_}++' -- -ws="$WS" | head -40)"
  terr="$(grep -E '^\[ERROR\]|FAILURE|Caused by:' "$logs/test.log" | grep -vE "$NOISE" | perl -sne 's/\Q$ws\E\///g; s/\s+$//; $_ = substr($_,0,400); print "$_\n" unless $seen{$_}++' -- -ws="$WS" | head -40)"
  tsum="$(grep -E 'Tests run:.*Fail' "$logs/test.log" | tail -1 | perl -pe 's/^\[\w+\]\s*//; s/\s+$//')"

  local ok=""
  [ $ce -eq 0 ] && [ $te -eq 0 ] && [ -z "$issues" ] && ok=1
  printf '{"verify_report":{'
  printf '"java":%s,"maven":%s,' "$(jstr "$jv")" "$(jstr "$mv")"
  printf '"compile_exit":%s,"test_exit":%s,"tests_summary":%s,' "$ce" "$te" "$(jstr "$tsum")"
  printf '"compile_errors":%s,"test_errors":%s,' "$(printf '%s' "$cerr" | jlist)" "$(printf '%s' "$terr" | jlist)"
  printf '"residual_issues":%s,' "$(printf '%s' "$issues" | jlist)"
  printf '"log_dir":%s},' "$(jstr "$logs")"
  printf '"migration_complete":%s}\n' "$(jbool "$ok")"
}

export WS
"$MODE"
