import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from dotenv import load_dotenv
from .ai_service import ai_service
from .tools.web_scraper import scrape_webpage

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class WebTestAgent:
    def __init__(self):
        self.ai_service = ai_service
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # Check Playwright availability
        self.playwright_available = self._check_playwright()
        
        if self.playwright_available:
            print("🧪 Web Test Agent initialized (SPA support enabled)")
        else:
            print("🧪 Web Test Agent initialized (fallback mode - limited SPA support)")
            print("   ℹ️  Install Playwright for full React/Vue/Angular support:")
            print("      pip install playwright")
            print("      python -m playwright install chromium")
    
    def _check_playwright(self) -> bool:
        try:
            import playwright
            import shutil
            sys_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
            return sys_chromium is not None
        except ImportError:
            return False

    def _get_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "url": None,
                "page_data": None,
                "features": None,
                "test_cases": None,
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
                if not url.startswith("http"):
                    url = "https://" + url
                return url
        return None

    def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        clear_history: bool = False,
    ) -> Dict[str, Any]:
        thinking_steps = []
        session_id = session_id or f"webtest_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        session = self._get_session(session_id)

        if clear_history:
            self.sessions[session_id] = {
                "url": None,
                "page_data": None,
                "features": None,
                "test_cases": None,
                "history": [],
            }
            session = self.sessions[session_id]

        url = self._extract_url(query)

        if url and (not session["url"] or url != session["url"]):
            thinking_steps.append({
                "type": "tool_call",
                "content": f"Scraping webpage: {url}",
                "tool_name": "web_scraper",
                "tool_input": url,
            })

            page_data = scrape_webpage(url)

            if not page_data.get("success"):
                error_msg = page_data.get("error", "Unknown error")
                thinking_steps.append({
                    "type": "error",
                    "content": f"Failed to scrape: {error_msg}",
                    "tool_name": "web_scraper",
                    "tool_input": None,
                })
                return {
                    "success": False,
                    "response": f"I couldn't access the webpage at **{url}**.\n\nError: {error_msg}\n\nPlease check that the URL is correct and the site is accessible.",
                    "thinking_steps": thinking_steps,
                    "session_id": session_id,
                }

            session["url"] = url
            session["page_data"] = page_data

            thinking_steps.append({
                "type": "tool_result",
                "content": f"Successfully scraped page: {page_data.get('title', 'Untitled')} — "
                           f"{page_data['page_stats']['total_buttons']} buttons, "
                           f"{page_data['page_stats']['total_forms']} forms, "
                           f"{page_data['page_stats']['total_links']} links, "
                           f"{page_data['page_stats']['total_inputs']} inputs",
                "tool_name": "web_scraper",
                "tool_input": None,
            })

            thinking_steps.append({
                "type": "thinking",
                "content": "Extracting features from the page structure...",
                "tool_name": None,
                "tool_input": None,
            })

            features = self._extract_features(page_data)
            session["features"] = features

            thinking_steps.append({
                "type": "tool_result",
                "content": f"Identified {len(features)} features from the webpage",
                "tool_name": "feature_extractor",
                "tool_input": None,
            })

            test_output = self._generate_test_cases_sequential(page_data, features, url, thinking_steps)
            session["test_cases"] = test_output

            session["history"].append({"role": "user", "content": query})
            session["history"].append({"role": "assistant", "content": test_output})

            return {
                "success": True,
                "response": test_output,
                "thinking_steps": thinking_steps,
                "session_id": session_id,
            }

        elif session.get("page_data"):
            thinking_steps.append({
                "type": "thinking",
                "content": f"Follow-up question about {session['url']}",
                "tool_name": None,
                "tool_input": None,
            })

            followup_response = self._handle_followup(query, session)

            session["history"].append({"role": "user", "content": query})
            session["history"].append({"role": "assistant", "content": followup_response})

            return {
                "success": True,
                "response": followup_response,
                "thinking_steps": thinking_steps,
                "session_id": session_id,
            }
        else:
            return {
                "success": True,
                "response": (
                    "Welcome to the **Web Test Agent**! 🧪\n\n"
                    "I can analyze any webpage and generate comprehensive test cases for it.\n\n"
                    "**How to use:**\n"
                    "1. Paste a webpage URL (e.g., `https://example.com/login`)\n"
                    "2. I'll scrape the page and identify all features\n"
                    "3. I'll generate:\n"
                    "   - **Feature list** with descriptions\n"
                    "   - **Manual test cases** (step-by-step)\n"
                    "   - **Automated test cases** (structured)\n"
                    "   - **Test scripts** (Selenium/Playwright code)\n\n"
                    "Go ahead — paste a URL to get started!"
                ),
                "thinking_steps": [],
                "session_id": session_id,
            }

    def _extract_features(self, page_data: Dict[str, Any]) -> List[Dict[str, str]]:
        page_summary = self._build_page_summary(page_data)

        prompt = f"""You are a QA analyst. Analyze this webpage structure and extract ALL user-facing features.

PAGE DATA:
{page_summary}

Return a JSON array of features. Each feature should have:
- "id": Feature ID like F001, F002, etc.
- "name": Short feature name
- "description": What the feature does
- "category": One of: Navigation, Form, Authentication, Display, Interactive, Data, Media, Accessibility
- "elements": Relevant HTML elements involved

Return ONLY the JSON array, no other text. Example:
[
  {{"id": "F001", "name": "User Login Form", "description": "Allows users to log in with email and password", "category": "Authentication", "elements": ["email input", "password input", "submit button"]}}
]"""

        try:
            result = self.ai_service.call_genai(prompt, temperature=0.3, max_tokens=4096)
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                features = json.loads(json_match.group(0))
                return features
        except Exception as e:
            print(f"Feature extraction error: {e}")

        return self._fallback_feature_extraction(page_data)

    def _generate_test_cases_sequential(
        self, page_data: Dict, features: List[Dict], url: str, thinking_steps: List[Dict]
    ) -> str:
        features_text = ""
        for f in features:
            features_text += f"- **{f.get('id', '')}**: {f.get('name', '')} — {f.get('description', '')}\n"

        page_summary = self._build_page_summary(page_data)
        title = page_data.get('title', 'Web Application')
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M')

        base_context = (
            f"**Target URL:** {url}\n"
            f"**Page Title:** {title}\n\n"
            f"**IDENTIFIED FEATURES:**\n{features_text}\n"
            f"**PAGE STRUCTURE:**\n{page_summary}"
        )

        header = (
            f"# Test Report: {title}\n\n"
            f"**Application URL:** {url}\n"
            f"**Report Date:** {report_date}\n"
            f"**Prepared By:** Web Test Agent (AI-Powered QA)\n\n---\n\n"
        )

        sections = []

        section_configs = [
            {
                "name": "Executive Summary",
                "section_num": 1,
                "heading": "## 1. Executive Summary",
                "thinking": "Generating Executive Summary...",
                "prompt": f"""You are a senior QA Lead. Based on the following webpage analysis, generate ONLY the Executive Summary section.

{base_context}

Generate a Markdown section titled "## 1. Executive Summary".

Write a professional 3-5 sentence summary that covers:
- What application/page was analyzed
- The scope of testing (what types of tests were produced)
- Key findings about the page structure and testability
- Overall test coverage approach

Be specific to this page's actual content and features.
Return ONLY this section, nothing else.""",
            },
            {
                "name": "Feature Inventory",
                "section_num": 2,
                "heading": "## 2. Feature Inventory",
                "thinking": "Generating Feature Inventory table...",
                "prompt": f"""You are a senior QA Lead. Based on the following webpage analysis, generate ONLY the Feature Inventory section.

{base_context}

Generate a Markdown section titled "## 2. Feature Inventory" with ALL features in a proper Markdown table:

| Feature ID | Feature Name | Category | Description | Priority |
|------------|-------------|----------|-------------|----------|
| F001 | ... | ... | ... | High/Medium/Low |

Include every identified feature. Assign priority based on user impact (authentication/forms = High, display = Medium, minor UI = Low).
Use clean Markdown formatting. Return ONLY this section, nothing else.""",
            },
            {
                "name": "Manual Test Cases",
                "section_num": 3,
                "heading": "## 3. Manual Test Cases",
                "thinking": "Generating Manual Test Cases for each feature...",
                "prompt": f"""You are a senior QA Lead. Based on the following webpage analysis, generate ONLY the Manual Test Cases section.

{base_context}

Generate a Markdown section titled "## 3. Manual Test Cases".

For EACH feature, create a sub-section with test cases in table format:

### 3.X [Feature Name]

| Field | Details |
|-------|---------|
| **Test Case ID** | TC001 |
| **Title** | [What is being tested] |
| **Priority** | High / Medium / Low |
| **Preconditions** | [Setup required] |
| **Test Steps** | 1. Step one 2. Step two 3. Step three |
| **Expected Result** | [What should happen] |
| **Type** | Positive / Negative / Edge Case |

Include at least 2-3 test cases per feature (positive, negative, and edge case).
Test steps must be specific and actionable using real page elements.
Return ONLY this section, nothing else.""",
            },
            {
                "name": "Automated Test Cases",
                "section_num": 4,
                "heading": "## 4. Automated Test Cases",
                "thinking": "Generating Automated Test Cases...",
                "prompt": f"""You are a senior QA Lead. Based on the following webpage analysis, generate ONLY the Automated Test Cases section.

{base_context}

Generate a Markdown section titled "## 4. Automated Test Cases".

For each feature, write structured automated test case descriptions:

For each test case include:
- Test Case ID (ATC-001, ATC-002, etc.)
- Feature being tested
- Test objective
- Preconditions
- Test steps (numbered)
- Expected result
- Test data required
- Automation feasibility notes

Group test cases by feature. Cover positive, negative, and boundary scenarios.
Use real element selectors and page structure details in the steps.
Return ONLY this section, nothing else.""",
            },
            {
                "name": "Automated Test Matrix",
                "section_num": 5,
                "heading": "## 5. Automated Test Matrix",
                "thinking": "Generating Automated Test Matrix summary...",
                "prompt": f"""You are a senior QA Lead. Based on the following webpage analysis, generate ONLY the Automated Test Matrix section.

{base_context}

Generate a Markdown section titled "## 5. Automated Test Matrix".

Present a summary matrix of all automated tests in a Markdown table:

| Test ID | Feature | Test Type | Action | Expected Assertion | Test Data |
|---------|---------|-----------|--------|-------------------|-----------|
| AT001 | ... | Functional/UI/Boundary | ... | ... | ... |

Cover all features with appropriate automated tests. Include functional, UI validation, and boundary test types.
Use real selectors and element names from the page structure.
Return ONLY this section, nothing else.""",
            },
            {
                "name": "Selenium Test Script",
                "section_num": 6,
                "heading": "## 6. Selenium Test Script (Python)",
                "thinking": "Generating Selenium test script (Python)...",
                "prompt": f"""You are a senior QA automation engineer. Based on the following webpage analysis, generate ONLY a Selenium test script.

{base_context}

Generate a Markdown section titled "## 6. Selenium Test Script (Python)".

Write a clean, production-ready Selenium test script using pytest and Page Object Model pattern.
Wrap the entire script in a single ```python code block. Include:
- All necessary imports (selenium, pytest, WebDriverWait, expected_conditions)
- A Page Object class with locators based on actual page elements
- A test class with descriptive test method names
- Proper WebDriverWait usage for dynamic elements
- setUp/tearDown with Chrome WebDriver
- Clear docstrings
- Tests for ALL identified features

Use real selectors from the page structure (IDs, names, CSS selectors) where possible.
Return ONLY this section, nothing else.""",
            },
            {
                "name": "Playwright Test Script",
                "section_num": 7,
                "heading": "## 7. Playwright Test Script (JavaScript)",
                "thinking": "Generating Playwright test script (JavaScript)...",
                "prompt": f"""You are a senior QA automation engineer. Based on the following webpage analysis, generate ONLY a Playwright test script.

{base_context}

Generate a Markdown section titled "## 7. Playwright Test Script (JavaScript)".

Write a clean Playwright test script in JavaScript.
Wrap the entire script in a single ```javascript code block. Include:
- Proper test.describe blocks grouping related tests
- beforeEach hook to navigate to the page
- afterEach hook for cleanup
- Descriptive test names matching features
- Proper assertions (expect) and modern selectors (getByRole, getByLabel, getByText)
- Tests for ALL identified features
- Error handling and edge case tests

Use real selectors from the page structure where possible.
Return ONLY this section, nothing else.""",
            },
        ]

        for config in section_configs:
            thinking_steps.append({
                "type": "thinking",
                "content": config["thinking"],
                "tool_name": None,
                "tool_input": None,
            })

            try:
                result = self.ai_service.call_genai(config["prompt"], temperature=0.4, max_tokens=8192)
                result = self._enforce_section_heading(result, config["heading"])
                sections.append(result)
                thinking_steps.append({
                    "type": "tool_result",
                    "content": f"{config['name']} generated successfully",
                    "tool_name": "test_generator",
                    "tool_input": None,
                })
            except Exception as e:
                error_msg = f"Error generating {config['name']}: {str(e)}"
                sections.append(f"{config['heading']}\n\n_{error_msg}_\n")
                thinking_steps.append({
                    "type": "error",
                    "content": error_msg,
                    "tool_name": "test_generator",
                    "tool_input": None,
                })

        return header + "\n\n".join(sections)

    def _enforce_section_heading(self, content: str, expected_heading: str) -> str:
        content = content.strip()
        lines = content.split('\n')
        body_lines = []
        found_body = False
        for line in lines:
            if not found_body and re.match(r'^#{1,3}\s+', line.strip()):
                continue
            if not found_body and line.strip() == '':
                continue
            if not found_body and line.strip() == '---':
                continue
            found_body = True
            if re.match(r'^##\s+\d+\.\s+', line.strip()):
                continue
            body_lines.append(line)
        body = '\n'.join(body_lines).strip()
        return f"{expected_heading}\n\n{body}"

    def _handle_followup(self, query: str, session: Dict) -> str:
        history_text = ""
        for msg in session["history"][-6:]:
            history_text += f"\n{msg['role'].upper()}: {msg['content'][:500]}\n"

        features_text = ""
        if session.get("features"):
            for f in session["features"]:
                features_text += f"- {f.get('id', '')}: {f.get('name', '')} — {f.get('description', '')}\n"

        prompt = f"""You are a senior QA engineer. The user has already analyzed a webpage and you generated test cases.

URL: {session.get('url', 'N/A')}
Page Title: {session.get('page_data', {}).get('title', 'N/A')}

IDENTIFIED FEATURES:
{features_text}

CONVERSATION HISTORY:
{history_text}

USER'S FOLLOW-UP:
{query}

Respond helpfully. If they ask for:
- More test cases for a specific feature: generate them
- A different testing framework: generate appropriate scripts
- Clarification: explain the test cases
- Modification: update the test cases as requested
- API tests, performance tests, etc.: generate those

Use well-formatted Markdown. Be thorough and specific."""

        try:
            result = self.ai_service.call_genai(prompt, temperature=0.4, max_tokens=8192)
            return result
        except Exception as e:
            return f"Error processing follow-up: {str(e)}"

    def _build_page_summary(self, page_data: Dict) -> str:
        parts = []
        parts.append(f"Title: {page_data.get('title', 'N/A')}")
        parts.append(f"Description: {page_data.get('meta_description', 'N/A')}")

        stats = page_data.get("page_stats", {})
        parts.append(f"\nPage Stats: {stats.get('total_forms', 0)} forms, "
                     f"{stats.get('total_buttons', 0)} buttons, "
                     f"{stats.get('total_links', 0)} links, "
                     f"{stats.get('total_inputs', 0)} standalone inputs, "
                     f"{stats.get('total_images', 0)} images")

        navs = page_data.get("navigation", [])
        if navs:
            parts.append("\nNavigation:")
            for nav in navs[:3]:
                items = [item["text"] for item in nav.get("items", [])[:10]]
                parts.append(f"  [{nav.get('label', 'main')}]: {', '.join(items)}")

        headings = page_data.get("headings", [])
        if headings:
            parts.append("\nHeadings:")
            for h in headings[:15]:
                parts.append(f"  {h['level']}: {h['text']}")

        forms = page_data.get("forms", [])
        if forms:
            parts.append("\nForms:")
            for i, form in enumerate(forms):
                parts.append(f"  Form {i+1} (action={form.get('action','')}, method={form.get('method','')}):")
                for field in form.get("fields", []):
                    label_text = ""
                    if field.get("name") or field.get("id"):
                        for lbl in form.get("labels", []):
                            if lbl.get("for") and (lbl["for"] == field.get("id") or lbl["for"] == field.get("name")):
                                label_text = f" label='{lbl['text']}'"
                                break
                    parts.append(f"    - {field['tag']} type={field.get('type','')} "
                                 f"name={field.get('name','')} placeholder={field.get('placeholder','')}"
                                 f"{label_text}"
                                 f"{' [required]' if field.get('required') else ''}")
                    if field.get("options"):
                        parts.append(f"      options: {', '.join(field['options'])}")
                if form.get("labels") and not any(f.get("name") for f in form.get("fields", [])):
                    parts.append(f"    Labels: {', '.join(l['text'] for l in form['labels'])}")
                if form.get("submit_button"):
                    parts.append(f"    Submit: {form['submit_button']}")

        buttons = page_data.get("buttons", [])
        if buttons:
            parts.append(f"\nButtons ({len(buttons)}):")
            for btn in buttons[:20]:
                parts.append(f"  - '{btn['text']}' type={btn.get('type','')} id={btn.get('id','')}")

        inputs = page_data.get("inputs", [])
        if inputs:
            parts.append(f"\nStandalone Inputs ({len(inputs)}):")
            for inp in inputs[:15]:
                parts.append(f"  - {inp['tag']} type={inp.get('type','')} "
                             f"name={inp.get('name','')} placeholder={inp.get('placeholder','')}")

        interactive = page_data.get("interactive_elements", [])
        if interactive:
            parts.append(f"\nInteractive Elements ({len(interactive)}):")
            for el in interactive[:10]:
                parts.append(f"  - role={el.get('role','')} id={el.get('id','')} "
                             f"label={el.get('aria_label','')} preview={el.get('text_preview','')[:50]}")

        sections = page_data.get("text_sections", [])
        if sections:
            parts.append(f"\nContent Sections ({len(sections)}):")
            for sec in sections[:10]:
                parts.append(f"  - [{sec['tag']}] {sec.get('heading','No heading')}: "
                             f"{sec.get('content_preview','')[:100]}")

        return "\n".join(parts)

    def _fallback_feature_extraction(self, page_data: Dict) -> List[Dict]:
        features = []
        fid = 1

        for nav in page_data.get("navigation", []):
            features.append({
                "id": f"F{fid:03d}",
                "name": f"Navigation — {nav.get('label', 'Main')}",
                "description": f"Navigation with {len(nav.get('items', []))} links",
                "category": "Navigation",
                "elements": [item["text"] for item in nav.get("items", [])[:5]],
            })
            fid += 1

        for i, form in enumerate(page_data.get("forms", [])):
            field_names = [f.get("name") or f.get("placeholder") or f.get("type") for f in form.get("fields", [])]
            features.append({
                "id": f"F{fid:03d}",
                "name": f"Form — {form.get('submit_button', 'Submit')}",
                "description": f"Form with fields: {', '.join(filter(None, field_names))}",
                "category": "Form",
                "elements": field_names,
            })
            fid += 1

        for btn in page_data.get("buttons", []):
            if btn.get("text"):
                features.append({
                    "id": f"F{fid:03d}",
                    "name": f"Button — {btn['text']}",
                    "description": f"Interactive button: {btn['text']}",
                    "category": "Interactive",
                    "elements": [btn["text"]],
                })
                fid += 1

        return features


web_test_agent = WebTestAgent()
