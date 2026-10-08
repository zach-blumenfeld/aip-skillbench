"""Shared scan/rewrite logic for the spring-boot-3-migration AIP skill.

Stdlib only (Python 3.8+). Every entry script reads one JSON object on stdin
({"currentState", "assets", "expects"}) and prints one JSON object.
"""
import json
import os
import re
import shutil
import sys

EDIT_EXTS = (".java", ".kt", ".properties", ".yml", ".yaml", ".xml")
TEXT_EXTS = EDIT_EXTS + (".gradle", ".kts")


# ----------------------------------------------------------------- plumbing
def read_payload():
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    state = payload.get("currentState") or {}
    assets = payload.get("assets") or {}
    cfg = assets.get("config")
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    if not cfg:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "assets", "config.json")) as fh:
            cfg = json.load(fh)
    cfg = dict(cfg)
    # Optional state overrides for target versions.
    for key in ("target_boot_version", "target_java_version"):
        if state.get(key):
            cfg[key] = str(state[key])
    return state, cfg


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def fail(msg):
    emit({"error": msg})
    sys.exit(1)


def project_root(state):
    root = state.get("project_dir")
    if not root:
        fail("state.project_dir is required (absolute path to the Maven/Gradle project root, e.g. /workspace)")
    root = os.path.expanduser(str(root))
    if not os.path.isabs(root):
        fail("project_dir must be an absolute path (scripts run with cwd = the skill's scripts/ folder): %r" % root)
    if not os.path.isdir(root):
        fail("project_dir does not exist or is not a directory: %s" % root)
    return os.path.realpath(root)


def walk(root, cfg, exts=TEXT_EXTS):
    skip = set(cfg.get("skip_dirs", []))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(exts):
                yield os.path.join(dirpath, fn)


def read(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(text)


def rel(root, path):
    return os.path.relpath(path, root)


def java_num(v):
    v = (v or "").strip()
    m = re.match(r"^(?:1\.)?(\d+)$", v)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------- pom
DEP_RE = re.compile(r"<dependency>.*?</dependency>", re.S)


def tag(block, name):
    m = re.search(r"<%s>\s*([^<]*?)\s*</%s>" % (re.escape(name), re.escape(name)), block)
    return m.group(1) if m else None


def section_spans(text, name):
    return [(m.start(), m.end()) for m in re.finditer(r"<%s>.*?</%s>" % (name, name), text, re.S)]


def in_spans(pos, spans):
    return any(a <= pos < b for a, b in spans)


def pom_dependencies(text):
    managed = section_spans(text, "dependencyManagement")
    plugins = section_spans(text, "plugins")
    out = []
    for m in DEP_RE.finditer(text):
        b = m.group(0)
        out.append({
            "groupId": tag(b, "groupId"),
            "artifactId": tag(b, "artifactId"),
            "version": tag(b, "version"),
            "scope": tag(b, "scope"),
            "managed": in_spans(m.start(), managed),
            "plugin_dep": in_spans(m.start(), plugins),
            "start": m.start(),
            "end": m.end(),
        })
    return out


def pom_facts(text):
    facts = {"boot_version": None, "boot_version_source": None, "java_version": None}
    for m in re.finditer(r"<parent>.*?</parent>", text, re.S):
        if "spring-boot-starter-parent" in m.group(0):
            facts["boot_version"] = tag(m.group(0), "version")
            facts["boot_version_source"] = "parent"
    if not facts["boot_version"]:
        m = re.search(r"<artifactId>spring-boot-dependencies</artifactId>\s*<version>([^<]+)</version>", text)
        if m:
            facts["boot_version"] = m.group(1).strip()
            facts["boot_version_source"] = "bom"
    if not facts["boot_version"]:
        m = re.search(r"<spring-boot\.version>([^<]+)</spring-boot\.version>", text)
        if m:
            facts["boot_version"] = m.group(1).strip()
            facts["boot_version_source"] = "property"
    for key in ("java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target"):
        v = tag(text, key)
        if v:
            facts["java_version"] = v
            break
    return facts


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _dep_xml(indent, g, a, v=None, scope=None):
    inner = indent + "    "
    s = "%s<dependency>\n%s<groupId>%s</groupId>\n%s<artifactId>%s</artifactId>\n" % (indent, inner, g, inner, a)
    if v:
        s += "%s<version>%s</version>\n" % (inner, v)
    if scope:
        s += "%s<scope>%s</scope>\n" % (inner, scope)
    return s + "%s</dependency>" % indent


def _block_with_indent(text, start, end, eat_comment=True):
    """Expand a dependency span to whole lines; include a preceding JAXB/activation comment line."""
    ls = text.rfind("\n", 0, start) + 1
    indent = text[ls:start]
    if indent.strip():
        ls, indent = start, ""
    le = text.find("\n", end)
    le = len(text) if le == -1 else le + 1
    # preceding comment line that only describes the removed dependency
    prev_end = ls - 1
    prev_start = text.rfind("\n", 0, max(prev_end, 0)) + 1 if prev_end > 0 else 0
    prev = text[prev_start:prev_end] if prev_end > 0 else ""
    if eat_comment and re.match(r"^\s*<!--.*-->\s*$", prev) and re.search(r"(?i)jaxb|activation|xml\.?bind", prev):
        ls = prev_start
    return ls, le, indent


def rewrite_pom(text, cfg, needs_xml_bind):
    changes = []
    target_boot = cfg["target_boot_version"]
    target_java = str(cfg["target_java_version"])
    min_java = int(cfg.get("min_java_version", 17))

    # 1. Spring Boot version (parent, BOM, or property)
    def bump_parent(m):
        block = m.group(0)
        if "spring-boot-starter-parent" not in block:
            return block
        v = tag(block, "version")
        if v and re.match(r"^[12]\.", v):
            changes.append("spring-boot-starter-parent %s -> %s" % (v, target_boot))
            return re.sub(r"<version>\s*[^<]*\s*</version>", "<version>%s</version>" % target_boot, block, count=1)
        return block
    text = re.sub(r"<parent>.*?</parent>", bump_parent, text, flags=re.S)

    def bump_bom(m):
        if re.match(r"^[12]\.", m.group(2).strip()):
            changes.append("spring-boot-dependencies BOM %s -> %s" % (m.group(2).strip(), target_boot))
            return m.group(1) + target_boot + m.group(3)
        return m.group(0)
    text = re.sub(r"(<artifactId>spring-boot-dependencies</artifactId>\s*<version>)([^<]+)(</version>)", bump_bom, text)
    text = re.sub(r"(<spring-boot\.version>)([^<]+)(</spring-boot\.version>)", bump_bom, text)

    # 2. Java version properties and compiler-plugin config
    def bump_java(m):
        n = java_num(m.group(2))
        if n is not None and n < min_java:
            changes.append("%s %s -> %s" % (m.group(1).strip("<>"), m.group(2), target_java))
            return m.group(1) + target_java + m.group(3)
        return m.group(0)
    for key in ("java.version", "maven.compiler.source", "maven.compiler.target", "maven.compiler.release"):
        k = re.escape(key)
        text = re.sub(r"(<%s>)\s*([^<$]+?)\s*(</%s>)" % (k, k), bump_java, text)

    def bump_compiler_plugin(m):
        block = m.group(0)
        if "maven-compiler-plugin" not in block:
            return block
        for key in ("source", "target", "release"):
            block = re.sub(r"(<%s>)\s*([^<$]+?)\s*(</%s>)" % (key, key), bump_java, block)
        return block
    text = re.sub(r"<plugin>.*?</plugin>", bump_compiler_plugin, text, flags=re.S)

    # 3. Remove old JAXB / activation dependencies; replace legacy jjwt
    removals = cfg.get("remove_dependencies", [])
    for dep in sorted(pom_dependencies(text), key=lambda d: -d["start"]):
        g, a = dep["groupId"] or "", dep["artifactId"] or ""
        hit = [r for r in removals if r["groupId"] == g and r["artifactId"] in ("*", a)]
        if hit:
            ls, le, _ = _block_with_indent(text, dep["start"], dep["end"])
            text = text[:ls] + text[le:]
            changes.append("removed dependency %s:%s (%s)" % (g, a, hit[0]["why"]))
            continue
        if g == "io.jsonwebtoken" and a == "jjwt":
            ls, le, indent = _block_with_indent(text, dep["start"], dep["end"], eat_comment=False)
            v = cfg["jjwt_version"]
            repl = "\n".join([
                _dep_xml(indent, "io.jsonwebtoken", "jjwt-api", v),
                _dep_xml(indent, "io.jsonwebtoken", "jjwt-impl", v, "runtime"),
                _dep_xml(indent, "io.jsonwebtoken", "jjwt-jackson", v, "runtime"),
            ]) + "\n"
            text = text[:ls] + repl + text[le:]
            changes.append("replaced io.jsonwebtoken:jjwt:%s with jjwt-api/jjwt-impl/jjwt-jackson %s" % (dep["version"], v))

    # 4. Add Jakarta XML Bind only when the code actually uses XML binding
    if needs_xml_bind:
        have = {(d["groupId"], d["artifactId"]) for d in pom_dependencies(text) if not d["managed"]}
        wanted = [d for d in cfg.get("jakarta_xml_bind_dependencies", []) if (d["groupId"], d["artifactId"]) not in have]
        if wanted:
            blocked = section_spans(text, "dependencyManagement") + section_spans(text, "build") + section_spans(text, "profiles")
            closes = [m for m in re.finditer(r"</dependencies>", text) if not in_spans(m.start(), blocked)]
            if closes:
                pos = closes[0].start()
                ls = text.rfind("\n", 0, pos) + 1
                close_indent = text[ls:pos] if not text[ls:pos].strip() else ""
                indent = close_indent + "    "
                add = "\n".join(_dep_xml(indent, d["groupId"], d["artifactId"]) for d in wanted) + "\n"
                text = text[:ls] + add + text[ls:]
                changes.append("added %s (code uses XML binding)" % ", ".join(d["artifactId"] for d in wanted))
    if changes:
        text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text, changes


# --------------------------------------------------------- source rewrites
def javax_auto_regex(cfg):
    pk = [re.escape(p) for p in cfg["javax_auto_packages"] if p != "transaction"]
    ann = "|".join(re.escape(c) for c in cfg["javax_annotation_auto_classes"])
    return re.compile(
        r"\bjavax\.(?:(%s)\b|(transaction)\b(?!\.xa)|(annotation\.(?:%s))\b)" % ("|".join(pk), ann)
    )


def javax_manual_regex(cfg):
    pk = "|".join(re.escape(p) for p in cfg["javax_manual_packages"])
    return re.compile(r"\bjavax\.(%s)\b" % pk)


SOURCE_REWRITES = [
    # (rule, regex, replacement, extensions)
    ("security.enable-method-security", re.compile(r"\bEnableGlobalMethodSecurity\b"), "EnableMethodSecurity", (".java", ".kt")),
    ("security.ant-matchers", re.compile(r"\.antMatchers\("), ".requestMatchers(", (".java", ".kt")),
    ("security.mvc-matchers", re.compile(r"\.mvcMatchers\("), ".requestMatchers(", (".java", ".kt")),
    ("security.authorize-http-requests", re.compile(r"\.authorizeRequests\("), ".authorizeHttpRequests(", (".java", ".kt")),
    ("hibernate.update-from", re.compile(r"(?i)\b(update)\s+from\s+(?=[A-Za-z_])"), r"\1 ", (".java", ".kt")),
]


def rewrite_source(path, text, cfg):
    changes = []
    is_build = os.path.basename(path) in ("pom.xml",) or path.endswith((".gradle", ".kts"))
    if is_build:
        return text, changes
    auto = javax_auto_regex(cfg)

    def to_jakarta(m):
        return "jakarta." + (m.group(1) or m.group(2) or m.group(3))
    new, n = auto.subn(to_jakarta, text)
    if n:
        changes.append(("jakarta.namespace", n))
        text = new
    for rule, rx, repl, exts in SOURCE_REWRITES:
        if path.endswith(exts):
            new, n = rx.subn(repl, text)
            if n:
                changes.append((rule, n))
                text = new
    return text, changes


# ------------------------------------------------------------------- scan
def _rules(cfg):
    auto = javax_auto_regex(cfg)
    manual = javax_manual_regex(cfg)
    J = (".java", ".kt")
    CFG = (".properties", ".yml", ".yaml")
    return [
        # rule, area, severity, regex, extensions, fix
        ("jakarta.javax-ee", "jakarta", "blocking", auto, J + CFG + (".xml",),
         "Change javax.<EE package> to jakarta.<package> (apply-rewrites does this; JDK packages such as javax.sql, javax.crypto, javax.net, javax.transaction.xa stay javax)."),
        ("jakarta.javax-manual", "jakarta", "blocking", manual, J,
         "Java EE package with no automatic rewrite: switch import to jakarta.* AND swap the Maven dependency to its Jakarta artifact."),
        ("jakarta.annotation-wildcard", "jakarta", "blocking", re.compile(r"import\s+javax\.annotation\.\*\s*;"), J,
         "Replace the wildcard with explicit imports: jakarta.annotation.{PostConstruct,PreDestroy,Resource}; keep JDK/jsr305 javax.annotation classes as they are."),
        ("security.websecurityconfigureradapter", "security", "blocking", re.compile(r"WebSecurityConfigurerAdapter"), J,
         "Remove the adapter: plain @Configuration class with a SecurityFilterChain @Bean (lambda DSL) and AuthenticationManager from AuthenticationConfiguration. Also reword comments that name it (verification greps match comments)."),
        ("security.enable-global-method-security", "security", "blocking", re.compile(r"EnableGlobalMethodSecurity"), J,
         "Use @EnableMethodSecurity(prePostEnabled = true) and import ...method.configuration.EnableMethodSecurity."),
        ("security.legacy-matchers", "security", "blocking", re.compile(r"\.(antMatchers|mvcMatchers)\("), J,
         "Use .requestMatchers(...)."),
        ("security.regex-matchers", "security", "blocking", re.compile(r"\.regexMatchers\("), J,
         "Use .requestMatchers(RegexRequestMatcher.regexMatcher(\"...\")) (a plain string to requestMatchers is an ant/mvc pattern, not a regex)."),
        ("security.authorize-requests", "security", "blocking", re.compile(r"\.authorizeRequests\("), J,
         "Use .authorizeHttpRequests(auth -> auth ...)."),
        ("security.authentication-manager-bean", "security", "blocking", re.compile(r"authenticationManagerBean\s*\("), J,
         "Expose AuthenticationManager via @Bean authenticationManager(AuthenticationConfiguration c) { return c.getAuthenticationManager(); }."),
        ("security.configure-auth-builder", "security", "blocking", re.compile(r"configure\s*\(\s*AuthenticationManagerBuilder"), J,
         "Delete it: the UserDetailsService and PasswordEncoder beans are auto-detected."),
        ("security.chained-dsl", "security", "blocking",
         re.compile(r"\.(csrf|cors|sessionManagement|exceptionHandling|headers|frameOptions|httpBasic|formLogin|logout|rememberMe|oauth2Login|oauth2ResourceServer|authorizeHttpRequests|requiresChannel|anonymous)\(\s*\)"), J,
         "Convert to lambda DSL, e.g. .csrf(csrf -> csrf.disable()), .headers(h -> h.frameOptions(f -> f.disable())). No .and()."),
        ("security.and-chaining", "security", "blocking", re.compile(r"\.and\(\s*\)"), J,
         "Lambda DSL has no .and(); each configurer is its own lambda argument.", ),
        ("security.access-string", "security", "blocking", re.compile(r"\.access\(\s*\""), J,
         "authorizeHttpRequests has no access(String): use .access(new WebExpressionAuthorizationManager(\"...\")) or hasRole/hasAnyRole/hasAuthority."),
        ("http.resttemplate", "http-client", "blocking", re.compile(r"(?<![A-Za-z])(?<!Test)(?:Async)?RestTemplate(?:Builder)?\b"), J,
         "Migrate to RestClient (fluent get()/post()/delete() ... retrieve() ... body()/toBodilessEntity()). Reword comments that name RestTemplate too."),
        ("hibernate.legacy-criteria", "hibernate", "blocking", re.compile(r"org\.hibernate\.Criteria\b|\.createCriteria\(|org\.hibernate\.criterion\."), J,
         "Rewrite with JPA Criteria (CriteriaBuilder/CriteriaQuery/Root via EntityManager)."),
        ("hibernate.type-annotation", "hibernate", "blocking", re.compile(r"@Type\s*\(\s*type\s*="), J,
         "Hibernate 6 removed @Type(type=...): use @JdbcTypeCode(SqlTypes.JSON) or @Type(MyType.class)."),
        ("hibernate.typedef", "hibernate", "blocking", re.compile(r"@TypeDefs?\b"), J,
         "@TypeDef removed in Hibernate 6: delete it and use @Type(Class) / @JdbcTypeCode on the field."),
        ("hibernate.update-from", "hibernate", "blocking", re.compile(r"(?i)\bupdate\s+from\s+[A-Za-z_]"), J,
         "Hibernate 6 HQL rejects 'update from X': write 'update X u set ...'."),
        ("hibernate.distinct-join-fetch", "hibernate", "advisory", re.compile(r"(?i)select\s+distinct\b.*\bjoin\s+fetch\b"), J,
         "DISTINCT is no longer needed with join fetch in Hibernate 6 (duplicates filtered automatically); optional cleanup."),
        ("hibernate.id-generation-auto", "hibernate", "advisory", re.compile(r"@GeneratedValue\s*(\(\s*\)|\(\s*strategy\s*=\s*GenerationType\.AUTO\s*\)|$)"), J,
         "Hibernate 6 changed the AUTO default (per-entity <entity>_SEQ sequences). Prefer explicit GenerationType.IDENTITY, or SEQUENCE with @SequenceGenerator(allocationSize = 1)."),
        ("hibernate.temporal", "hibernate", "advisory", re.compile(r"@Temporal\b"), J,
         "Prefer java.time types (LocalDateTime) over java.util.Date + @Temporal."),
        ("jwt.parser-builder", "jwt", "blocking", re.compile(r"Jwts\.parser\(\)\s*\.\s*(setSigningKey|parseClaimsJws|parse\b)"), J,
         "jjwt 0.12: Jwts.parser() returns a builder: Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload()."),
        ("jwt.textcodec", "jwt", "blocking", re.compile(r"io\.jsonwebtoken\.impl\.TextCodec|\bTextCodec\."), J,
         "TextCodec is gone in jjwt 0.12: use io.jsonwebtoken.io.Decoders.BASE64 / Keys.hmacShaKeyFor(bytes)."),
        ("jwt.signature-algorithm", "jwt", "advisory", re.compile(r"\bSignatureAlgorithm\.\w+"), J,
         "Deprecated in jjwt 0.12: signWith(Keys.hmacShaKeyFor(secretBytes)) (HS keys must be >= 256 bits or WeakKeyException)."),
        ("jakarta.datatype-converter", "jakarta", "advisory", re.compile(r"\bDatatypeConverter\b"), J,
         "Prefer java.util.Base64 over (jakarta|javax).xml.bind.DatatypeConverter so the code needs no XML-binding dependency."),
        ("config.dialect", "hibernate", "advisory", re.compile(r"(spring\.jpa\.database-platform|hibernate\.dialect)\s*[=:]"), CFG,
         "Hibernate 6 auto-detects the dialect from the JDBC URL; the property can usually be removed (unversioned H2Dialect/PostgreSQLDialect/MySQLDialect are still valid, leaving them is fine). Versioned dialects (MySQL57Dialect, PostgreSQL95Dialect, ...) must become MySQLDialect / PostgreSQLDialect."),
        ("config.versioned-dialect", "hibernate", "blocking", re.compile(r"org\.hibernate\.dialect\.(MySQL5\w*|MySQL8\w*|MariaDB10\w*|PostgreSQL9\w*|PostgreSQL10\w*|Oracle1\w*|SQLServer20\w*|H2Dialect\w+)"), CFG + J,
         "Versioned dialect classes were removed/renamed in Hibernate 6: use MySQLDialect, MariaDBDialect, PostgreSQLDialect, OracleDialect, SQLServerDialect, H2Dialect (or drop the property)."),
        ("config.persistence-xml-namespace", "jakarta", "blocking", re.compile(r"xmlns(:\w+)?=\"https?://(xmlns\.jcp\.org|java\.sun\.com)/xml/ns/(persistence|javaee)"), (".xml",),
         "Update XML descriptors to Jakarta namespaces (persistence: https://jakarta.ee/xml/ns/persistence, version=\"3.0\")."),
    ]


def _comment_line(line):
    s = line.strip()
    return s.startswith(("//", "*", "/*", "#", "<!--"))


def scan(root, cfg, waived=None):
    waived = set(waived or [])
    issues = []
    inv = {
        "project_dir": root,
        "build_tool": None,
        "poms": [],
        "java_files": 0,
        "test_java_files": 0,
        "files_with_javax_ee": [],
        "entity_files": [],
        "security_config_files": [],
        "method_security_annotations": False,
        "enable_method_security_present": False,
        "security_filter_chain_present": False,
        "resttemplate_files": [],
        "restclient_present": False,
        "uses_xml_bind": False,
        "jakarta_persistence_imports": False,
        "config_files": [],
        "maven_executable": None,
        "maven_wrapper": False,
        "jdks": [],
    }
    rules = _rules(cfg)

    def add(rule, area, severity, path, line_no, match, fix):
        iid = "%s@%s:%s" % (rule, rel(root, path) if path else "-", line_no or 0)
        if iid in waived:
            return
        issues.append({"id": iid, "area": area, "severity": severity,
                       "file": rel(root, path) if path else None, "line": line_no,
                       "match": (match or "")[:200], "fix": fix})

    # -- build files
    poms = list(p for p in walk(root, cfg, (".xml",)) if os.path.basename(p) == "pom.xml")
    gradles = list(p for p in walk(root, cfg, (".gradle", ".kts")) if os.path.basename(p).startswith("build.gradle"))
    inv["build_tool"] = "maven" if poms else ("gradle" if gradles else None)
    if not poms and not gradles:
        add("build.no-build-file", "build", "blocking", None, None, "", "No pom.xml or build.gradle found under project_dir; point project_dir at the project root.")
    min_java = int(cfg.get("min_java_version", 17))
    for pom in poms:
        text = read(pom)
        facts = pom_facts(text)
        deps = pom_dependencies(text)
        inv["poms"].append({"file": rel(root, pom), "boot_version": facts["boot_version"],
                            "java_version": facts["java_version"],
                            "dependencies": ["%s:%s%s" % (d["groupId"], d["artifactId"], ":" + d["version"] if d["version"] else "")
                                             for d in deps if not d["plugin_dep"]]})
        bv = facts["boot_version"]
        if bv and re.match(r"^[12]\.", bv):
            add("build.boot-version", "build", "blocking", pom, line_of(text, text.find(bv)), bv, "Set Spring Boot to %s." % cfg["target_boot_version"])
        elif bv and bv.startswith("${"):
            add("build.boot-version-property", "build", "blocking", pom, None, bv, "Boot version is a property reference; set the property to %s." % cfg["target_boot_version"])
        for key in ("java.version", "maven.compiler.source", "maven.compiler.target", "maven.compiler.release"):
            v = tag(text, key)
            n = java_num(v)
            if n is not None and n < min_java:
                add("build.java-version", "build", "blocking", pom, line_of(text, text.find("<%s>" % key)), "%s=%s" % (key, v),
                    "Spring Boot 3 requires Java 17+; set %s to %s." % (key, cfg["target_java_version"]))
        for d in deps:
            g, a, v = d["groupId"] or "", d["artifactId"] or "", d["version"] or ""
            ln = line_of(text, d["start"])
            if any(r["groupId"] == g and r["artifactId"] in ("*", a) for r in cfg.get("remove_dependencies", [])):
                add("build.old-jaxb-activation", "build", "blocking", pom, ln, "%s:%s" % (g, a),
                    "Remove this Java EE dependency (javax JAXB/activation conflicts with Jakarta in Boot 3).")
            if g == "io.jsonwebtoken" and a == "jjwt":
                add("build.legacy-jjwt", "jwt", "blocking", pom, ln, "%s:%s:%s" % (g, a, v),
                    "Replace with jjwt-api + jjwt-impl (runtime) + jjwt-jackson (runtime) %s." % cfg["jjwt_version"])
            key = "%s:%s" % (g, a)
            if key in cfg.get("javax_artifact_replacements", {}):
                add("build.javax-artifact", "build", "blocking", pom, ln, key, cfg["javax_artifact_replacements"][key])
            if a == "spring-boot-maven-plugin" and re.match(r"^[12]\.", v):
                add("build.boot-plugin-version", "build", "blocking", pom, ln, v, "Drop the explicit version (inherit from the Boot 3 parent).")
            if a == "hibernate-core" and re.match(r"^[1-5]\.", v):
                add("build.hibernate-version", "hibernate", "blocking", pom, ln, v, "Drop the explicit hibernate-core version; Boot 3 manages Hibernate 6 (org.hibernate.orm group).")
            if a == "spring-boot-starter-actuator":
                add("config.actuator", "config", "advisory", pom, ln, key,
                    "Actuator endpoint paths/exposure changed in Boot 3; re-check which actuator paths the SecurityFilterChain permits.")
        for m in re.finditer(r"<artifactId>spring-boot-maven-plugin</artifactId>\s*<version>([12]\.[^<]*)</version>", text):
            add("build.boot-plugin-version", "build", "blocking", pom, line_of(text, m.start()), m.group(1), "Drop the explicit plugin version (inherit from the Boot 3 parent).")
    for g in gradles:
        text = read(g)
        if re.search(r"org\.springframework\.boot['\"]?\)?\s*version\s*['\"]2\.", text) or "javax.xml.bind" in text or re.search(r"sourceCompatibility\s*=\s*['\"]?(1\.8|8|11)\b", text):
            add("build.gradle-manual", "build", "blocking", g, None, os.path.basename(g),
                "Gradle build: set org.springframework.boot plugin to %s, Java toolchain/sourceCompatibility %s, remove javax.xml.bind/jaxb/activation deps, replace jjwt with jjwt-api/impl/jackson %s." % (cfg["target_boot_version"], cfg["target_java_version"], cfg["jjwt_version"]))

    # -- sources and config
    has_method_sec_annotations = False
    files_text = {}
    for path in walk(root, cfg, EDIT_EXTS):
        if os.path.basename(path) == "pom.xml":
            continue
        text = read(path)
        files_text[path] = text
        r = rel(root, path)
        if path.endswith((".java", ".kt")):
            inv["java_files"] += 1
            if os.sep + "test" + os.sep in path:
                inv["test_java_files"] += 1
            if re.search(r"^\s*@Entity\b", text, re.M):
                inv["entity_files"].append(r)
            if re.search(r"@EnableWebSecurity|SecurityFilterChain|WebSecurityConfigurerAdapter|HttpSecurity", text):
                inv["security_config_files"].append(r)
            if re.search(r"@(PreAuthorize|PostAuthorize|PreFilter|PostFilter|Secured|RolesAllowed)\b", text):
                has_method_sec_annotations = True
            if re.search(r"^\s*@EnableMethodSecurity\b", text, re.M):
                inv["enable_method_security_present"] = True
            if re.search(r"^\s*(public\s+)?SecurityFilterChain\s+\w+\s*\(", text, re.M):
                inv["security_filter_chain_present"] = True
            if re.search(r"import\s+org\.springframework\.web\.client\.RestClient\s*;|\bRestClient\.(create|builder)\(", text):
                inv["restclient_present"] = True
            if re.search(r"\b(javax|jakarta)\.xml\.bind\b", text):
                inv["uses_xml_bind"] = True
            if re.search(r"import\s+jakarta\.persistence\.", text):
                inv["jakarta_persistence_imports"] = True
            if re.search(r"^\s*@EnableWebSecurity\b", text, re.M) and not re.search(r"^\s*@Configuration\b", text, re.M):
                add("security.missing-configuration", "security", "blocking", path, line_of(text, text.find("@EnableWebSecurity")), "@EnableWebSecurity",
                    "Spring Security 6: @EnableWebSecurity no longer implies @Configuration; add @Configuration.")
        elif path.endswith((".properties", ".yml", ".yaml")):
            inv["config_files"].append(r)
        lines = text.split("\n")
        is_security_file = "org.springframework.security" in text
        for rule, area, severity, rx, exts, fix in rules:
            if not path.endswith(exts):
                continue
            if rule.startswith("security.") and not is_security_file:
                continue
            for i, line in enumerate(lines, 1):
                m = rx.search(line)
                if not m:
                    continue
                if rule == "jakarta.javax-ee" and r not in inv["files_with_javax_ee"]:
                    inv["files_with_javax_ee"].append(r)
                if rule == "http.resttemplate" and r not in inv["resttemplate_files"]:
                    inv["resttemplate_files"].append(r)
                f = fix
                if _comment_line(line) and severity == "blocking":
                    f = "Comment/Javadoc names a removed API: reword it. " + fix
                add(rule, area, severity, path, i, line.strip(), f)

    inv["method_security_annotations"] = has_method_sec_annotations
    if has_method_sec_annotations and not inv["enable_method_security_present"]:
        add("security.method-security-missing", "security", "blocking", None, None, "@PreAuthorize/@Secured used",
            "Method-security annotations are used but no class has @EnableMethodSecurity(prePostEnabled = true); add it to the security config.")
    sec_dep = any("spring-boot-starter-security" in d for p in inv["poms"] for d in p["dependencies"])
    if (sec_dep or inv["security_config_files"]) and inv["security_config_files"] and not inv["security_filter_chain_present"]:
        add("security.filter-chain-missing", "security", "blocking", None, None, "no SecurityFilterChain bean",
            "Define @Bean SecurityFilterChain securityFilterChain(HttpSecurity http) that ends with return http.build();")
    if inv["entity_files"] and not inv["jakarta_persistence_imports"]:
        add("jakarta.persistence-missing", "jakarta", "blocking", None, None, "entities without jakarta.persistence imports",
            "Every JPA entity must import jakarta.persistence.*; the migration is incomplete.")

    # -- environment facts for the build step
    mvn = shutil.which("mvn")
    for cand in ("/root/.sdkman/candidates/maven/current/bin/mvn", os.path.expanduser("~/.sdkman/candidates/maven/current/bin/mvn")):
        if not mvn and os.path.exists(cand):
            mvn = cand
    inv["maven_executable"] = mvn
    inv["maven_wrapper"] = os.path.exists(os.path.join(root, "mvnw"))
    for base in ("/root/.sdkman/candidates/java", os.path.expanduser("~/.sdkman/candidates/java")):
        if os.path.isdir(base):
            inv["jdks"] = sorted(set(inv["jdks"]) | {os.path.join(base, d) for d in os.listdir(base) if d != "current"})
    return inv, issues


def summarize(issues):
    by = {}
    for i in issues:
        k = "%s/%s" % (i["area"], i["severity"])
        by[k] = by.get(k, 0) + 1
    return by
