import json
import logging
from typing import Dict, Any, List

from .ai_service import ai_service
from .tools.owasp_mapper import get_owasp_checklist, map_finding_to_owasp, OWASP_TOP_10
from .tools.report_builder import parse_llm_findings
from prompts import prompt_loader

logger = logging.getLogger(__name__)


def analyze_tls(url: str, tls_info: Dict) -> List[Dict]:
    findings = []
    if not tls_info:
        return findings

    if not tls_info.get("uses_https"):
        if not tls_info.get("http_to_https_redirect"):
            findings.append({
                "title": "No HTTPS — Cleartext HTTP Communication",
                "severity": "High",
                "owasp_category": "A02:2021 — Cryptographic Failures",
                "location": url,
                "description": "The target is served over HTTP without redirecting to HTTPS. All data is transmitted in cleartext.",
                "evidence": f"URL scheme is HTTP. No HTTP→HTTPS redirect detected.",
                "recommendation": "Enable HTTPS with a valid TLS certificate and redirect all HTTP traffic to HTTPS.",
            })
        else:
            findings.append({
                "title": "HTTP→HTTPS Redirect Present",
                "severity": "Informational",
                "owasp_category": "A02:2021 — Cryptographic Failures",
                "location": url,
                "description": "The site redirects HTTP to HTTPS, which is good practice.",
                "evidence": "HTTP request returned a redirect to HTTPS.",
                "recommendation": "Ensure HSTS header is also set to prevent downgrade attacks.",
            })

    if tls_info.get("certificate_valid") is False:
        findings.append({
            "title": "Invalid TLS Certificate",
            "severity": "Critical",
            "owasp_category": "A02:2021 — Cryptographic Failures",
            "location": url,
            "description": "The TLS certificate failed validation.",
            "evidence": f"TLS certificate validation failed. Version: {tls_info.get('tls_version', 'Unknown')}",
            "recommendation": "Install a valid TLS certificate from a trusted Certificate Authority.",
        })

    tls_ver = tls_info.get("tls_version", "")
    if tls_ver and ("TLSv1.0" in tls_ver or "TLSv1.1" in tls_ver or "SSLv" in tls_ver):
        findings.append({
            "title": f"Outdated TLS Version: {tls_ver}",
            "severity": "High",
            "owasp_category": "A02:2021 — Cryptographic Failures",
            "location": url,
            "description": f"The server uses {tls_ver}, which is deprecated and vulnerable.",
            "evidence": f"TLS negotiation returned version: {tls_ver}",
            "recommendation": "Upgrade to TLS 1.2 or TLS 1.3.",
        })

    return findings


def analyze_missing_headers(web_ctx: Dict) -> List[Dict]:
    findings = []
    missing = web_ctx.get("missing_security_headers", [])
    header_info = {
        "Content-Security-Policy": ("High", "A05:2021 — Security Misconfiguration", "No CSP header — browser has no restrictions on loading external resources, making XSS easier.", "Implement a strict CSP. Start with 'default-src self'."),
        "Strict-Transport-Security": ("High", "A02:2021 — Cryptographic Failures", "No HSTS — browsers may connect over HTTP, enabling SSL-stripping.", "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains'."),
        "X-Content-Type-Options": ("Medium", "A05:2021 — Security Misconfiguration", "No X-Content-Type-Options — browsers may MIME-sniff responses.", "Add 'X-Content-Type-Options: nosniff'."),
        "X-Frame-Options": ("Medium", "A05:2021 — Security Misconfiguration", "No X-Frame-Options — page can be embedded in iframes (clickjacking).", "Add 'X-Frame-Options: DENY' or 'SAMEORIGIN'."),
        "Referrer-Policy": ("Low", "A05:2021 — Security Misconfiguration", "No Referrer-Policy — may leak URL parameters to external sites.", "Add 'Referrer-Policy: strict-origin-when-cross-origin'."),
        "Permissions-Policy": ("Low", "A05:2021 — Security Misconfiguration", "No Permissions-Policy — browser features not explicitly restricted.", "Add Permissions-Policy to restrict features."),
        "X-XSS-Protection": ("Informational", "A05:2021 — Security Misconfiguration", "Legacy XSS protection not set.", "Add 'X-XSS-Protection: 1; mode=block' for older browsers."),
    }
    raw_snapshot = web_ctx.get("raw_headers_snapshot", "")
    first_header = True
    for h in missing:
        info = header_info.get(h)
        if info:
            finding = {
                "title": f"Missing {h} Header",
                "severity": info[0],
                "owasp_category": info[1],
                "location": "HTTP Response Headers",
                "description": info[2],
                "evidence": f"The '{h}' header was not present in the HTTP response.",
                "recommendation": info[3],
            }
            if raw_snapshot and first_header:
                finding["evidence_snapshot"] = {
                    "type": "http_headers",
                    "label": f"HTTP response headers — '{h}' is absent",
                    "response_headers": raw_snapshot,
                }
                first_header = False
            findings.append(finding)
    return findings


def analyze_cookies(web_ctx: Dict) -> List[Dict]:
    findings = []
    for cookie in web_ctx.get("cookies", []):
        if not cookie.get("secure"):
            findings.append({
                "title": f"Cookie '{cookie['name']}' Missing Secure Flag",
                "severity": "Medium",
                "owasp_category": "A02:2021 — Cryptographic Failures",
                "location": f"Cookie: {cookie['name']}",
                "description": f"Cookie '{cookie['name']}' can be sent over unencrypted HTTP.",
                "evidence": f"Set-Cookie for '{cookie['name']}' without Secure attribute.",
                "recommendation": "Set the Secure flag on all cookies.",
            })
        if not cookie.get("httponly"):
            findings.append({
                "title": f"Cookie '{cookie['name']}' Missing HttpOnly Flag",
                "severity": "Medium",
                "owasp_category": "A07:2021 — Identification and Authentication Failures",
                "location": f"Cookie: {cookie['name']}",
                "description": f"Cookie '{cookie['name']}' is accessible via JavaScript.",
                "evidence": f"Set-Cookie for '{cookie['name']}' without HttpOnly attribute.",
                "recommendation": "Set HttpOnly flag on session cookies.",
            })
    return findings


def analyze_cors(web_ctx: Dict) -> List[Dict]:
    findings = []
    cors = web_ctx.get("security_headers", {}).get("Access-Control-Allow-Origin")
    if cors == "*":
        finding = {
            "title": "Overly Permissive CORS Policy (Wildcard)",
            "severity": "High",
            "owasp_category": "A01:2021 — Broken Access Control",
            "location": "CORS Configuration",
            "description": "Server sends 'Access-Control-Allow-Origin: *', allowing any website to make cross-origin requests.",
            "evidence": "HTTP response contains 'Access-Control-Allow-Origin: *'.",
            "recommendation": "Restrict CORS to specific trusted origins.",
        }
        raw_snapshot = web_ctx.get("raw_headers_snapshot", "")
        if raw_snapshot:
            finding["evidence_snapshot"] = {
                "type": "http_headers",
                "label": "HTTP response shows wildcard CORS header",
                "response_headers": raw_snapshot,
            }
        findings.append(finding)
    return findings


def analyze_forms_from_list(forms: List[Dict]) -> List[Dict]:
    findings = []
    for i, form in enumerate(forms, 1):
        if form.get("method") == "POST" and not form.get("has_csrf_token"):
            action = form.get("action", form.get("action_url", "(no action)"))
            page = form.get("page_url", "")
            findings.append({
                "title": f"Form Missing CSRF Protection",
                "severity": "Medium",
                "owasp_category": "A01:2021 — Broken Access Control",
                "location": f"POST form on {page or action}",
                "description": f"A POST form (action='{action}') has no visible CSRF token, potentially vulnerable to CSRF attacks.",
                "evidence": f"Form uses POST with {len(form.get('inputs', []))} inputs but no csrf/token input detected.",
                "recommendation": "Add CSRF token protection to all state-changing forms.",
            })
    return findings


def llm_analyze(url: str, web_ctx: Dict, web_summary: str, all_forms: List, all_api_endpoints: List) -> List[Dict]:
    if not all_forms and not web_ctx.get("cookies") and not all_api_endpoints:
        return []

    owasp_checklist = get_owasp_checklist()

    prompt = prompt_loader.get_prompt("shannon_security_agent.yml", "llm_analyze").format(
        url=url,
        num_forms=len(all_forms),
        forms_json=json.dumps(all_forms[:10], indent=2),
        cookies_json=json.dumps(web_ctx.get('cookies', []), indent=2),
        num_endpoints=len(all_api_endpoints),
        endpoints_json=json.dumps(all_api_endpoints[:20], indent=2),
        technologies_json=json.dumps(web_ctx.get('technologies', []), indent=2),
        comments_json=json.dumps(web_ctx.get('comments', []), indent=2)
    )

    llm_response = ai_service.call_genai(prompt, temperature=0.2, max_tokens=6096, task_name="security_analysis")

    if "NO ADDITIONAL FINDINGS" in llm_response.upper():
        return []

    findings = parse_llm_findings(llm_response)
    for f in findings:
        if not f.get("owasp_category") or f["owasp_category"] == "N/A":
            owasp_key = map_finding_to_owasp(f.get("title", "") + " " + f.get("description", ""))
            cat = OWASP_TOP_10.get(owasp_key, {})
            f["owasp_category"] = f"{cat.get('id', '')} — {cat.get('name', '')}"
    return findings
