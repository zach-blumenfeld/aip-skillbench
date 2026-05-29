#!/usr/bin/env python3
"""Scan a Java source tree for Spring Security 5 patterns that block migration to Spring Security 6.

Usage:
    python scripts/scan_legacy_patterns.py <project-root>

Emits one JSON object per pattern to stdout (one per line) summarizing
files and line numbers that hit each legacy pattern. Exit 0 means scan
ran successfully, regardless of whether legacy patterns were found.
The caller decides what to do with the results.
"""

import json
import re
import sys
from pathlib import Path

PATTERNS = [
    ("websecurityconfigureradapter",
     re.compile(r"extends\s+WebSecurityConfigurerAdapter\b"),
     "Class extends WebSecurityConfigurerAdapter. Must be refactored to a "
     "@Configuration class with a SecurityFilterChain @Bean."),
    ("websecurityconfigureradapter-import",
     re.compile(r"\bWebSecurityConfigurerAdapter\b"),
     "Reference to WebSecurityConfigurerAdapter (import or usage). "
     "Class no longer exists in Spring Security 6."),
    ("enable-global-method-security",
     re.compile(r"@EnableGlobalMethodSecurity\b"),
     "Replace with @EnableMethodSecurity (annotation + import)."),
    ("ant-matchers",
     re.compile(r"\.antMatchers\s*\("),
     "Replace .antMatchers(...) with .requestMatchers(...)."),
    ("mvc-matchers",
     re.compile(r"\.mvcMatchers\s*\("),
     "Replace .mvcMatchers(...) with .requestMatchers(...)."),
    ("regex-matchers",
     re.compile(r"\.regexMatchers\s*\("),
     "Replace .regexMatchers(...) with .requestMatchers(...)."),
    ("authorize-requests",
     re.compile(r"\.authorizeRequests\s*\("),
     "Replace .authorizeRequests(...) with .authorizeHttpRequests(...)."),
    ("authentication-manager-bean-override",
     re.compile(r"authenticationManagerBean\s*\("),
     "Override of authenticationManagerBean(): replace with an "
     "AuthenticationManager @Bean that calls "
     "AuthenticationConfiguration.getAuthenticationManager()."),
    ("javax-servlet-import",
     re.compile(r"^\s*import\s+javax\.servlet\.", re.MULTILINE),
     "javax.servlet.* import. Spring Security 6 / Spring Boot 3 use "
     "jakarta.servlet.* (Jakarta EE 9+)."),
    ("chained-csrf-disable",
     re.compile(r"\.csrf\s*\(\s*\)\s*\.disable\s*\(\s*\)"),
     "Chained .csrf().disable() style. Convert to lambda DSL: "
     ".csrf(csrf -> csrf.disable())."),
    ("chained-headers-frameoptions",
     re.compile(r"\.headers\s*\(\s*\)\s*\.frameOptions\s*\(\s*\)"),
     "Chained .headers().frameOptions() style. Convert to lambda DSL: "
     ".headers(h -> h.frameOptions(f -> f.disable()))."),
    ("chained-session-management",
     re.compile(r"\.sessionManagement\s*\(\s*\)\s*\."),
     "Chained .sessionManagement() style. Convert to lambda DSL: "
     ".sessionManagement(s -> s.sessionCreationPolicy(...))."),
    ("chained-exception-handling",
     re.compile(r"\.exceptionHandling\s*\(\s*\)\s*\."),
     "Chained .exceptionHandling() style. Convert to lambda DSL: "
     ".exceptionHandling(ex -> ex.authenticationEntryPoint(...))."),
]


def scan(root: Path) -> list[dict]:
    hits: dict[str, list[dict]] = {key: [] for key, _, _ in PATTERNS}
    for path in root.rglob("*.java"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for key, pattern, _ in PATTERNS:
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                hits[key].append({"file": str(path), "line": line_no})
    results = []
    for key, _, advice in PATTERNS:
        results.append({
            "pattern": key,
            "advice": advice,
            "count": len(hits[key]),
            "occurrences": hits[key],
        })
    return results


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: scan_legacy_patterns.py <project-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    for record in scan(root):
        print(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
