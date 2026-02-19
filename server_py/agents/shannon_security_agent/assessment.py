import logging
from typing import Dict, Any, List

from .tools.web_context import gather_web_context, summarize_web_context, validate_url
from .tools.report_builder import build_security_report
from .tools.crawler import crawl_site
from .tools.dir_enum import enumerate_directories
from .tools.injection_tester import test_form_injections
from .tools.method_tester import test_http_methods
from .tools.cve_lookup import lookup_cves
from .security_analyzers import (
    analyze_tls,
    analyze_missing_headers,
    analyze_cookies,
    analyze_cors,
    analyze_forms_from_list,
    llm_analyze,
)

logger = logging.getLogger(__name__)


def run_deep_assessment(session: Dict[str, Any]) -> Dict[str, Any]:
    url = session["url"]
    thinking_steps = []
    all_findings = []

    thinking_steps.append({
        "type": "thinking",
        "content": f"Phase 1: Pre-Reconnaissance — Validating target URL: {url}"
    })

    if not validate_url(url):
        response = (
            f"I couldn't validate the URL `{url}`. Please make sure:\n"
            "- It starts with `http://` or `https://`\n"
            "- It's a publicly accessible domain\n"
            "- It's not a local/private IP address"
        )
        session["history"].append({"role": "assistant", "content": response})
        session["url"] = None
        return {"success": False, "response": response}

    session["phase"] = "reconnaissance"
    thinking_steps.append({
        "type": "tool_call",
        "content": "Phase 2: Initial Reconnaissance — Fetching homepage, headers, TLS, cookies...",
        "tool_name": "web_context"
    })

    try:
        web_ctx = gather_web_context(url)
        session["web_context"] = web_ctx
    except Exception as e:
        response = f"Error during reconnaissance of `{url}`: {str(e)}"
        session["history"].append({"role": "assistant", "content": response})
        return {"success": False, "response": response, "thinking_steps": thinking_steps}

    recon_ok = web_ctx.get("recon_successful", False)
    recon_error = web_ctx.get("error")

    if not recon_ok and recon_error:
        thinking_steps.append({
            "type": "tool_result",
            "content": f"Reconnaissance FAILED: {recon_error}",
            "tool_name": "web_context"
        })

        tls_info = web_ctx.get("tls_info", {})
        tls_findings = analyze_tls(url, tls_info)

        web_summary = summarize_web_context(web_ctx)
        session["web_summary"] = web_summary
        session["findings"] = tls_findings

        report = build_security_report(
            url=url,
            findings=tls_findings,
            web_summary=web_summary,
            assessment_status="INCONCLUSIVE",
            recon_error=recon_error,
        )
        session["report"] = report
        session["phase"] = "complete"

        thinking_steps.append({
            "type": "thinking",
            "content": f"Assessment marked INCONCLUSIVE — reconnaissance failed. Only TLS checks performed. {len(tls_findings)} findings."
        })

        session["history"].append({"role": "assistant", "content": report})
        return {"success": True, "response": report, "thinking_steps": thinking_steps}

    web_summary = summarize_web_context(web_ctx)
    session["web_summary"] = web_summary

    thinking_steps.append({
        "type": "tool_result",
        "content": (
            f"Homepage recon complete (HTTP {web_ctx.get('status_code', '?')}). "
            f"{len(web_ctx.get('forms', []))} forms, {len(web_ctx.get('cookies', []))} cookies, "
            f"{len(web_ctx.get('missing_security_headers', []))} missing headers, "
            f"{len(web_ctx.get('technologies', []))} technologies"
        ),
        "tool_name": "web_context"
    })

    all_findings.extend(analyze_tls(url, web_ctx.get("tls_info", {})))
    all_findings.extend(analyze_missing_headers(web_ctx))
    all_findings.extend(analyze_cookies(web_ctx))
    all_findings.extend(analyze_cors(web_ctx))

    session["phase"] = "crawling"
    thinking_steps.append({
        "type": "tool_call",
        "content": "Phase 3: Site Crawling — Discovering all pages (max 30 pages, depth 3)...",
        "tool_name": "crawler"
    })

    try:
        crawl_result = crawl_site(url, max_pages=30, max_depth=3, time_budget=30)
        crawl_stats = crawl_result["stats"]

        thinking_steps.append({
            "type": "tool_result",
            "content": (
                f"Crawled {crawl_stats['pages_crawled']} pages, found {crawl_stats['total_urls_found']} URLs "
                f"(depth {crawl_stats['max_depth_reached']}) in {crawl_stats['time_elapsed']}s. "
                f"Discovered {len(crawl_result['forms_found'])} forms, {len(crawl_result['api_endpoints'])} API endpoints"
            ),
            "tool_name": "crawler"
        })

        for page in crawl_result["pages_crawled"]:
            if page["security_headers_missing"] and page["url"] != url:
                page_missing = page["security_headers_missing"]
                header_diff = set(page_missing) - set(web_ctx.get("missing_security_headers", []))
                for h in header_diff:
                    all_findings.append({
                        "title": f"Inconsistent Security Headers on {page['url']}",
                        "severity": "Medium",
                        "owasp_category": "A05:2021 — Security Misconfiguration",
                        "location": page["url"],
                        "description": f"The page at {page['url']} is missing the '{h}' header, while other pages may have it. Inconsistent security header deployment can leave some pages vulnerable.",
                        "evidence": f"Crawled page at depth {page['depth']} is missing header '{h}' in its response.",
                        "recommendation": "Ensure security headers are applied consistently across all pages via server-level configuration.",
                    })

        for cookie in crawl_result["cookies_collected"]:
            if not any(c["name"] == cookie["name"] for c in web_ctx.get("cookies", [])):
                if not cookie.get("secure"):
                    all_findings.append({
                        "title": f"Cookie '{cookie['name']}' Missing Secure Flag (discovered on {cookie.get('found_on', 'crawled page')})",
                        "severity": "Medium",
                        "owasp_category": "A02:2021 — Cryptographic Failures",
                        "location": f"Cookie: {cookie['name']} on {cookie.get('found_on', '')}",
                        "description": f"Cookie '{cookie['name']}' discovered during crawling does not have the Secure flag.",
                        "evidence": f"Set-Cookie for '{cookie['name']}' observed on {cookie.get('found_on', 'a crawled page')} without Secure attribute.",
                        "recommendation": "Set the Secure flag on all cookies.",
                    })

        all_forms = web_ctx.get("forms", []) + crawl_result.get("forms_found", [])
        all_api_endpoints = web_ctx.get("api_endpoints", []) + crawl_result.get("api_endpoints", [])

    except Exception as e:
        thinking_steps.append({
            "type": "tool_result",
            "content": f"Crawling failed: {str(e)[:100]}",
            "tool_name": "crawler"
        })
        all_forms = web_ctx.get("forms", [])
        all_api_endpoints = web_ctx.get("api_endpoints", [])

    session["phase"] = "dir_enum"
    thinking_steps.append({
        "type": "tool_call",
        "content": "Phase 4: Sensitive Path Discovery — Checking for exposed files, admin panels, backups...",
        "tool_name": "dir_enum"
    })

    try:
        dir_result = enumerate_directories(url, time_budget=25)

        accessible = dir_result["accessible_paths"]
        restricted = dir_result["interesting_responses"]
        robots = dir_result["robots_txt_entries"]

        thinking_steps.append({
            "type": "tool_result",
            "content": (
                f"Checked {dir_result['stats']['paths_checked']} paths in {dir_result['stats']['time_elapsed']}s. "
                f"Found {len(accessible)} accessible, {len(restricted)} restricted, "
                f"{len(robots)} robots.txt entries"
            ),
            "tool_name": "dir_enum"
        })

        sensitive_patterns = [".env", ".git", ".svn", ".htpasswd", "backup", ".sql", "credentials", "config", ".DS_Store"]
        for path_info in accessible:
            path = path_info["path"]
            is_sensitive = any(p in path.lower() for p in sensitive_patterns)
            severity = "Critical" if is_sensitive else "Medium"
            owasp = "A01:2021 — Broken Access Control" if is_sensitive else "A05:2021 — Security Misconfiguration"

            finding = {
                "title": f"Exposed Path: {path}",
                "severity": severity,
                "owasp_category": owasp,
                "location": path_info["url"],
                "description": f"{path_info['description']}. This path is publicly accessible and returned HTTP 200.",
                "evidence": (
                    f"HTTP GET {path_info['url']} returned status 200 with content-type '{path_info.get('content_type', 'N/A')}' "
                    f"and {path_info.get('content_length', 0)} bytes."
                ),
                "recommendation": "Restrict access to this path. Use authentication, remove the file from the web root, or block access via server configuration.",
            }
            if path_info.get("evidence_snapshot"):
                finding["evidence_snapshot"] = path_info["evidence_snapshot"]
            all_findings.append(finding)

    except Exception as e:
        thinking_steps.append({
            "type": "tool_result",
            "content": f"Directory enumeration failed: {str(e)[:100]}",
            "tool_name": "dir_enum"
        })

    session["phase"] = "injection_testing"
    if all_forms:
        thinking_steps.append({
            "type": "tool_call",
            "content": f"Phase 5: Active Injection Testing — Testing {len(all_forms)} forms with XSS and SQLi payloads...",
            "tool_name": "injection_tester"
        })

        try:
            injection_result = test_form_injections(all_forms, url, time_budget=30)

            xss_count = len(injection_result["xss_findings"])
            sqli_count = len(injection_result["sqli_findings"])

            thinking_steps.append({
                "type": "tool_result",
                "content": (
                    f"Tested {injection_result['forms_tested']} forms with {injection_result['payloads_sent']} payloads "
                    f"in {injection_result['stats']['time_elapsed']}s. "
                    f"Found {xss_count} XSS and {sqli_count} SQLi indicators"
                ),
                "tool_name": "injection_tester"
            })

            for xss in injection_result["xss_findings"]:
                finding = {
                    "title": f"Reflected XSS in '{xss['parameter']}' parameter",
                    "severity": "High",
                    "owasp_category": "A03:2021 — Injection",
                    "location": f"Form: {xss['form_url']} → {xss['action_url']} ({xss['method']})",
                    "description": f"{xss['description']}. The parameter '{xss['parameter']}' reflects user input without proper encoding, allowing script injection.",
                    "evidence": xss["evidence"],
                    "recommendation": "Encode all user input before rendering in HTML. Use context-appropriate encoding (HTML entity, JavaScript, URL). Implement a Content-Security-Policy header.",
                }
                if xss.get("evidence_snapshot"):
                    finding["evidence_snapshot"] = xss["evidence_snapshot"]
                all_findings.append(finding)

            for sqli in injection_result["sqli_findings"]:
                finding = {
                    "title": f"SQL Injection Indicator in '{sqli['parameter']}' parameter",
                    "severity": "Critical",
                    "owasp_category": "A03:2021 — Injection",
                    "location": f"Form: {sqli['form_url']} → {sqli['action_url']} ({sqli['method']})",
                    "description": f"{sqli['description']}. Database error messages in the response suggest user input is being passed to SQL queries without proper parameterization.",
                    "evidence": sqli["evidence"],
                    "recommendation": "Use parameterized queries or prepared statements. Never concatenate user input into SQL queries. Implement an ORM or query builder.",
                }
                if sqli.get("evidence_snapshot"):
                    finding["evidence_snapshot"] = sqli["evidence_snapshot"]
                all_findings.append(finding)

        except Exception as e:
            thinking_steps.append({
                "type": "tool_result",
                "content": f"Injection testing failed: {str(e)[:100]}",
                "tool_name": "injection_tester"
            })
    else:
        thinking_steps.append({
            "type": "thinking",
            "content": "Phase 5: Injection Testing — Skipped (no forms discovered to test)"
        })

    all_findings.extend(analyze_forms_from_list(all_forms))

    session["phase"] = "method_testing"
    test_paths = list(set(all_api_endpoints[:10] + ["/", "/api/"]))

    thinking_steps.append({
        "type": "tool_call",
        "content": f"Phase 6: HTTP Method Testing — Probing {len(test_paths)} endpoints for dangerous methods...",
        "tool_name": "method_tester"
    })

    try:
        method_result = test_http_methods(url, endpoints=test_paths, time_budget=15)

        thinking_steps.append({
            "type": "tool_result",
            "content": (
                f"Tested {method_result['stats']['endpoints_tested']} endpoints with "
                f"{method_result['stats']['methods_tested']} method probes in "
                f"{method_result['stats']['time_elapsed']}s. "
                f"Found {len(method_result['findings'])} issues"
            ),
            "tool_name": "method_tester"
        })

        all_findings.extend(method_result["findings"])

    except Exception as e:
        thinking_steps.append({
            "type": "tool_result",
            "content": f"Method testing failed: {str(e)[:100]}",
            "tool_name": "method_tester"
        })

    session["phase"] = "cve_lookup"
    all_tech = list(set(web_ctx.get("technologies", []) + crawl_result.get("technologies", []))) if 'crawl_result' in dir() else web_ctx.get("technologies", [])
    server_header = ""
    for t in all_tech:
        if t.startswith("Server: "):
            server_header = t.replace("Server: ", "")

    if all_tech or server_header:
        thinking_steps.append({
            "type": "tool_call",
            "content": f"Phase 7: CVE Lookup — Checking {len(all_tech)} detected technologies against known vulnerabilities...",
            "tool_name": "cve_lookup"
        })

        try:
            cve_result = lookup_cves(all_tech, server_header)

            thinking_steps.append({
                "type": "tool_result",
                "content": (
                    f"Analyzed {cve_result['stats']['technologies_analyzed']} technologies. "
                    f"Found {cve_result['stats']['cves_found']} known vulnerabilities"
                ),
                "tool_name": "cve_lookup"
            })

            all_findings.extend(cve_result["findings"])

            if server_header:
                all_findings.append({
                    "title": "Server Version Disclosure",
                    "severity": "Low",
                    "owasp_category": "A05:2021 — Security Misconfiguration",
                    "location": "Server HTTP Header",
                    "description": f"The server discloses its identity/version: '{server_header}'. This helps attackers target known vulnerabilities.",
                    "evidence": f"HTTP 'Server' header contains: '{server_header}'.",
                    "recommendation": "Remove or obfuscate the Server header.",
                })

        except Exception as e:
            thinking_steps.append({
                "type": "tool_result",
                "content": f"CVE lookup failed: {str(e)[:100]}",
                "tool_name": "cve_lookup"
            })
    else:
        thinking_steps.append({
            "type": "thinking",
            "content": "Phase 7: CVE Lookup — Skipped (no technology versions detected)"
        })

    session["phase"] = "llm_analysis"
    if all_forms or web_ctx.get("cookies") or all_api_endpoints:
        thinking_steps.append({
            "type": "tool_call",
            "content": "Phase 8: AI Deep Analysis — LLM reviewing all collected evidence for additional vulnerabilities...",
            "tool_name": "llm_analyzer"
        })

        try:
            llm_findings = llm_analyze(url, web_ctx, web_summary, all_forms, all_api_endpoints)
            thinking_steps.append({
                "type": "tool_result",
                "content": f"AI analysis found {len(llm_findings)} additional findings",
                "tool_name": "llm_analyzer"
            })
            all_findings.extend(llm_findings)
        except Exception as e:
            thinking_steps.append({
                "type": "tool_result",
                "content": f"AI analysis failed (non-fatal): {str(e)[:100]}",
                "tool_name": "llm_analyzer"
            })
    else:
        thinking_steps.append({
            "type": "thinking",
            "content": "Phase 8: AI Analysis — Skipped (no forms, cookies, or APIs to analyze beyond what's already checked)"
        })

    session["phase"] = "report"

    seen_titles = set()
    unique_findings = []
    for f in all_findings:
        key = f.get("title", "").lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            unique_findings.append(f)

    session["findings"] = unique_findings

    scan_stats = {
        "pages_crawled": crawl_result["stats"]["pages_crawled"] if 'crawl_result' in dir() else 0,
        "paths_checked": dir_result["stats"]["paths_checked"] if 'dir_result' in dir() else 0,
        "forms_tested": injection_result["forms_tested"] if 'injection_result' in dir() else 0,
        "payloads_sent": injection_result["payloads_sent"] if 'injection_result' in dir() else 0,
        "methods_probed": method_result["stats"]["methods_tested"] if 'method_result' in dir() else 0,
    }

    thinking_steps.append({
        "type": "tool_call",
        "content": f"Phase 9: Report Generation — Compiling {len(unique_findings)} unique findings from all phases...",
        "tool_name": "report_builder"
    })

    report = build_security_report(
        url=url,
        findings=unique_findings,
        web_summary=web_summary,
        repo_summary=session.get("repo_summary", ""),
        scan_stats=scan_stats,
    )
    session["report"] = report
    session["phase"] = "complete"

    thinking_steps.append({
        "type": "tool_result",
        "content": f"Deep assessment complete — {len(unique_findings)} evidence-backed findings across 8 scan phases",
        "tool_name": "report_builder"
    })

    session["history"].append({"role": "assistant", "content": report})
    return {
        "success": True,
        "response": report,
        "thinking_steps": thinking_steps,
    }
