# WA Site Research Script

This repository contains a command-line utility for enriching the Washington site
spreadsheet with ownership, acreage, contamination, and historical context using
the OpenAI Responses API with web search.

## Prerequisites

- Python 3.9 or later (tested with 3.11)
- An OpenAI API key with access to the `responses` endpoint and web search tools
- The input Excel workbook (e.g., `WA Sites, Viridian.xlsx`)

Install the Python dependencies once:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

If you prefer to keep dependencies isolated per project, you can run the above
commands inside a terminal that is integrated with editors such as Cursor or
Visual Studio Code.

## Running the script

1. Activate your virtual environment if you created one (see above).
2. Set your OpenAI API key in the environment. On Windows PowerShell:
   ```powershell
   $Env:OPENAI_API_KEY = "sk-..."
   ```
   On macOS/Linux bash or zsh:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
3. Invoke the script with the path to your input workbook and the desired
   output path. Example (PowerShell):
   ```powershell
   python wa_site_research.py "C:\Users\HannahRose_x3m0sef\OneDrive - Qi Venture Partners\Desktop\WA Sites, Viridian.xlsx" "C:\Users\HannahRose_x3m0sef\OneDrive - Qi Venture Partners\Desktop\WA Sites, Viridian - Enriched.xlsx"
   ```
   Example (macOS/Linux):
   ```bash
   python wa_site_research.py "./WA Sites, Viridian.xlsx" "./WA Sites, Viridian - Enriched.xlsx"
   ```

The script reads every row from the input workbook, queries the OpenAI API for
additional details, and writes a new workbook that contains the original data
plus the four new columns:

- `Current Owner`
- `Estimated Acreage`
- `Contamination`
- `History (1930-present)`

If the API cannot determine a value, the script writes `Unknown` in that cell.

## Frequently asked questions

### Can I run this alongside other Python programs?
Yes. This utility runs as a standalone Python process. As long as your machine
has sufficient resources and bandwidth, it can run concurrently with other
Python programs (for example, a script you are executing from Visual Studio
Code). Each script will use its own terminal or command window.

### Can I run it from Cursor or Visual Studio Code?
Absolutely. Open the repository folder in Cursor or VS Code, use the built-in
terminal, activate your virtual environment (if any), and run the command shown
above. The script does not require any special integration—any terminal capable
of running Python will work.

### How long will it take?
The script makes one API call per row. Each call can take several seconds
because it performs web searches. Expect the runtime to scale with the number of
rows in your spreadsheet.

### What happens if the API call fails?
The script automatically retries failed calls up to twice with exponential
backoff. If the API is still unreachable, the script stops and reports the
error.

## Troubleshooting tips

- If you see `OPENAI_API_KEY environment variable is not set`, double-check
  that you exported the key in the same terminal session where you run the
  script.
- If Excel cannot open the output file while the script is running, close the
  workbook before running the script so Python can write to it.
- When running on Windows, remember to use double quotes around file paths that
  contain spaces.
- `ModuleNotFoundError` indicates the dependencies were not installed—rerun the
  `pip install -r requirements.txt` command inside your virtual environment.

## Customising the model

Pass the `--model` flag to experiment with a different model ID:

```bash
python wa_site_research.py input.xlsx output.xlsx --model gpt-4.1
```

Refer to the OpenAI documentation for the list of available models in your
account.
