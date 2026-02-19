import os
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from dotenv import load_dotenv
from .ai_service import ai_service
from .assessment import run_deep_assessment
from prompts import prompt_loader

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class ShannonSecurityAgent:
    def __init__(self):
        self.ai_service = ai_service
        self.sessions: Dict[str, Dict[str, Any]] = {}
        print("🛡️ Shannon Security Agent initialized")

    def _get_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "url": None,
                "web_context": None,
                "web_summary": None,
                "repo_summary": None,
                "findings": None,
                "report": None,
                "phase": "idle",
                "history": [],
            }
        return self.sessions[session_id]

    def _extract_url(self, text: str) -> Optional[str]:
        patterns = [
            r'https?://[^\s<>"\'`,;)}\]]+',
            r'www\.[^\s<>"\'`,;)}\]]+',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                url = match.group(0).rstrip('.')
                if url.startswith('www.'):
                    url = 'https://' + url
                return url
        return None

    def _is_security_query(self, query: str) -> bool:
        keywords = [
            'security', 'pentest', 'penetration', 'vulnerability', 'vulnerabilities',
            'owasp', 'xss', 'injection', 'sqli', 'ssrf', 'exploit',
            'scan', 'assess', 'audit', 'attack', 'breach', 'hack',
            'secure', 'insecure', 'risk', 'threat', 'weakness',
        ]
        q_lower = query.lower()
        return any(kw in q_lower for kw in keywords)

    def process_query(self, query: str, session_id: str = "default") -> Dict[str, Any]:
        session = self._get_session(session_id)
        session["history"].append({"role": "user", "content": query})

        url = self._extract_url(query)
        q_lower = query.lower()

        if url and not session["url"]:
            session["url"] = url

        if not session["url"] and not session["report"]:
            if self._is_security_query(query):
                response = (
                    "I'm the Shannon Security Agent — I perform **deep AI-driven security assessments** "
                    "on web applications, inspired by the [Shannon pentesting framework](https://github.com/KeygraphHQ/shannon).\n\n"
                    "To get started, please provide:\n"
                    "- **A target URL** to assess (e.g., `https://your-app.com`)\n\n"
                    "My deep scan includes:\n"
                    "- **Full site crawling** — discovers all pages, not just the homepage\n"
                    "- **Sensitive path discovery** — checks for exposed files like `.env`, `.git`, `/admin`, API docs\n"
                    "- **Active injection testing** — sends safe XSS and SQL injection payloads to forms\n"
                    "- **HTTP method probing** — tests for dangerous methods (PUT, DELETE, TRACE)\n"
                    "- **TLS/HTTPS verification** — checks certificate validity and protocol version\n"
                    "- **Technology CVE lookup** — matches detected server versions against known vulnerabilities\n"
                    "- **OWASP Top 10 analysis** — comprehensive mapping of all findings\n\n"
                    "Just paste a URL and I'll begin the deep assessment."
                )
                session["history"].append({"role": "assistant", "content": response})
                return {"success": True, "response": response}
            else:
                response = self._ask_llm_general(query)
                session["history"].append({"role": "assistant", "content": response})
                return {"success": True, "response": response}

        if session["url"] and not session["web_context"]:
            return run_deep_assessment(session)

        if session["report"]:
            if any(kw in q_lower for kw in ['finding', 'detail', 'explain', 'more about', 'elaborate']):
                response = self._ask_about_findings(query, session)
                session["history"].append({"role": "assistant", "content": response})
                return {"success": True, "response": response}
            elif any(kw in q_lower for kw in ['rescan', 'scan again', 'reassess', 'new scan']):
                session["web_context"] = None
                session["web_summary"] = None
                session["findings"] = None
                session["report"] = None
                session["phase"] = "idle"
                return run_deep_assessment(session)
            elif url and url != session["url"]:
                session["url"] = url
                session["web_context"] = None
                session["web_summary"] = None
                session["findings"] = None
                session["report"] = None
                session["phase"] = "idle"
                return run_deep_assessment(session)
            else:
                response = self._ask_about_findings(query, session)
                session["history"].append({"role": "assistant", "content": response})
                return {"success": True, "response": response}

        return run_deep_assessment(session)

    def _ask_about_findings(self, query: str, session: Dict) -> str:
        findings_text = ""
        if session.get("findings"):
            for i, f in enumerate(session["findings"], 1):
                findings_text += f"\n{i}. {f.get('title', '')} ({f.get('severity', '')}): {f.get('description', '')}\n   Evidence: {f.get('evidence', 'N/A')}\n"

        prompt = prompt_loader.get_prompt("shannon_security_agent.yml", "followup_findings").format(
            url=session.get('url', 'N/A'),
            findings_text=findings_text,
            query=query
        )

        try:
            return self.ai_service.call_genai(prompt, temperature=0.5, max_tokens=6096)
        except Exception as e:
            return f"Error processing question: {str(e)}"

    def _ask_llm_general(self, query: str) -> str:
        prompt = prompt_loader.get_prompt("shannon_security_agent.yml", "general_response").format(
            query=query
        )

    def clear_session(self, session_id: str) -> Dict[str, Any]:
        if session_id in self.sessions:
            del self.sessions[session_id]
        return {"success": True, "message": "Session cleared"}


shannon_security_agent = ShannonSecurityAgent()
