 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/wa_site_research.py b/wa_site_research.py
new file mode 100644
index 0000000000000000000000000000000000000000..0717013c69da40ea742c41f12b3c8aed48ad07cf
--- /dev/null
+++ b/wa_site_research.py
@@ -0,0 +1,182 @@
+"""Utilities to enrich Washington site data via web-assisted research."""
+import argparse
+import json
+import os
+import time
+from dataclasses import dataclass
+from typing import Dict, Iterable, List, Optional
+
+import pandas as pd
+import requests
+
+
+OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
+DEFAULT_MODEL = "gpt-4.1-mini"
+
+
+class ResearchError(RuntimeError):
+    """Raised when the research API fails in a non-recoverable way."""
+
+
+@dataclass
+class SiteQuery:
+    site_name: str
+    address: str
+    city: str
+    state: str
+
+    def build_prompt(self) -> str:
+        """Return a detailed prompt instructing the model to research a site."""
+        return (
+            "You are a meticulous environmental researcher with access to live web search. "
+            "Use credible, up-to-date sources to answer the following questions about the "
+            "listed property. Provide concise answers that could fit in a spreadsheet. "
+            "If you cannot locate a data point after a good-faith search, return 'Unknown'.\n\n"
+            f"Site Name: {self.site_name}\n"
+            f"Address: {self.address}\n"
+            f"City: {self.city}\n"
+            f"State: {self.state}\n\n"
+            "For this site, research and answer the following: \n"
+            "1. Identify the current owner (include organization and, if available, a source).\n"
+            "2. Estimate the total acreage of the site (numeric figure and unit).\n"
+            "3. Summarize the contamination present (mention key pollutants).\n"
+            "4. Provide a brief 1930-present history (max 300 characters).\n\n"
+            "Respond using valid JSON with the following keys: \n"
+            "{\"owner\": string, \"acreage_estimate\": string, \"contamination\": string, \"history\": string}.\n"
+            "Keep the values concise (<= 300 characters each)."
+        )
+
+
+def call_openai(prompt: str, api_key: str, model: str = DEFAULT_MODEL, *, retries: int = 2, timeout: int = 60) -> Dict[str, str]:
+    """Call the OpenAI Responses API with web search enabled and return parsed JSON."""
+    headers = {
+        "Authorization": f"Bearer {api_key}",
+        "Content-Type": "application/json",
+    }
+    payload = {
+        "model": model,
+        "input": prompt,
+        "tools": [
+            {"type": "web_search"}
+        ],
+        "response_format": {
+            "type": "json_schema",
+            "json_schema": {
+                "name": "site_research",
+                "schema": {
+                    "type": "object",
+                    "properties": {
+                        "owner": {"type": "string"},
+                        "acreage_estimate": {"type": "string"},
+                        "contamination": {"type": "string"},
+                        "history": {"type": "string"},
+                    },
+                    "required": ["owner", "acreage_estimate", "contamination", "history"],
+                    "additionalProperties": False,
+                },
+            },
+        },
+    }
+
+    for attempt in range(retries + 1):
+        try:
+            response = requests.post(
+                OPENAI_RESPONSES_URL,
+                headers=headers,
+                json=payload,
+                timeout=timeout,
+            )
+            response.raise_for_status()
+            body = response.json()
+            if not body.get("output"):
+                raise ResearchError("Empty response body from OpenAI API")
+
+            # The JSON schema tool ensures the last output item contains the JSON string.
+            json_payload: Optional[str] = None
+            for item in body["output"]:
+                if item.get("type") == "output_json":
+                    json_payload = item.get("output")
+            if json_payload is None:
+                raise ResearchError("OpenAI response did not include JSON output")
+            parsed = json.loads(json_payload)
+            return {
+                "owner": parsed.get("owner", "Unknown").strip(),
+                "acreage_estimate": parsed.get("acreage_estimate", "Unknown").strip(),
+                "contamination": parsed.get("contamination", "Unknown").strip(),
+                "history": parsed.get("history", "Unknown").strip(),
+            }
+        except (requests.HTTPError, requests.Timeout, json.JSONDecodeError, ResearchError) as exc:
+            if attempt >= retries:
+                raise ResearchError(f"OpenAI request failed after {retries + 1} attempts") from exc
+            # Exponential backoff before retrying
+            sleep_for = 2 ** attempt
+            time.sleep(sleep_for)
+
+    raise ResearchError("Unexpected fall-through in call_openai")
+
+
+def enrich_sites(rows: Iterable[Dict[str, object]], api_key: str, *, model: str = DEFAULT_MODEL) -> List[Dict[str, object]]:
+    """Enrich each site row with research outputs."""
+    enriched_rows: List[Dict[str, object]] = []
+    for row in rows:
+        site = SiteQuery(
+            site_name=str(row.get("Site Name", "")),
+            address=str(row.get("Address", "")),
+            city=str(row.get("City", "")),
+            state=str(row.get("State", "")),
+        )
+        prompt = site.build_prompt()
+        answers = call_openai(prompt, api_key=api_key, model=model)
+        enriched_rows.append({
+            **row,
+            "Current Owner": answers["owner"],
+            "Estimated Acreage": answers["acreage_estimate"],
+            "Contamination": answers["contamination"],
+            "History (1930-present)": answers["history"],
+        })
+    return enriched_rows
+
+
+def load_rows_from_excel(path: str) -> List[Dict[str, object]]:
+    """Load rows from an Excel workbook into a list of dictionaries."""
+    df = pd.read_excel(path)
+    return df.to_dict(orient="records")
+
+
+def save_rows_to_excel(rows: List[Dict[str, object]], path: str) -> None:
+    """Write enriched rows back to an Excel workbook."""
+    df = pd.DataFrame(rows)
+    df.to_excel(path, index=False)
+
+
+def parse_args() -> argparse.Namespace:
+    parser = argparse.ArgumentParser(description="Enrich Washington site data via OpenAI research.")
+    parser.add_argument(
+        "input_path",
+        help="Path to the input Excel file (e.g., 'WA Sites, Viridian.xlsx')",
+    )
+    parser.add_argument(
+        "output_path",
+        help="Destination path for the enriched Excel file.",
+    )
+    parser.add_argument(
+        "--model",
+        default=DEFAULT_MODEL,
+        help="OpenAI model to use (default: %(default)s)",
+    )
+    return parser.parse_args()
+
+
+def main() -> None:
+    args = parse_args()
+    api_key = os.environ.get("OPENAI_API_KEY")
+    if not api_key:
+        raise SystemExit("OPENAI_API_KEY environment variable is not set.")
+
+    rows = load_rows_from_excel(args.input_path)
+    enriched_rows = enrich_sites(rows, api_key=api_key, model=args.model)
+    save_rows_to_excel(enriched_rows, args.output_path)
+
+
+if __name__ == "__main__":
+    main() 
EOF
)
