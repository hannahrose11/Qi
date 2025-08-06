import os
import json
import requests
import pandas as pd
from typing import Dict, List
import time
from datetime import datetime
import random
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from enum import Enum

# ====================================
# BUILT-IN CONFIGURATION
# ====================================

# Input/Output Fields (preserves your original structure)
ORIGINAL_COLUMNS = [
    "Case Name", "Plaintiff(s)", "Defendant(s)", "Plaintiff Industry", 
    "Plaintiff Industry (Broad)", "Defendant Industry", "Defendant Industry (Broad)",
    "Plaintiff Law Firm", "Defense Law Firm", "Estimated Annual Revenue of Plaintiff",
    "Estimated Annual Revenue of Defendant", "Case Stage", "Physical Injury Alleged",
    "Case Summary", "Harm Identified", "Harm Category", "Applicability Score", "Status"
]

# Industry Categories (built-in)
BROAD_CATEGORIES = [
    "Technology", "Healthcare", "Construction", "Insurance", "Manufacturing", 
    "Transportation", "Retail", "Financial Services", "Professional Services",
    "Real Estate", "Energy", "Hospitality", "Education", "Government", 
    "Non-Profit", "Other"
]

# Prompt Instructions (built-in) - Enhanced for reasoning
INDUSTRY_REASONING_PROMPT = """
You are an expert business analyst with deep reasoning capabilities. Your task is to determine the specific industries for companies involved in legal cases.

CASE: {case_name}
PLAINTIFF: {plaintiff}
DEFENDANT: {defendant}

REASONING PROCESS - Think step by step:

STEP 1: KNOWLEDGE ANALYSIS
- Use your extensive knowledge about companies, industries, and business patterns
- Consider company naming patterns and what they suggest about business type
- Think about the legal context - what types of companies typically have these disputes?

STEP 2: EVIDENCE EVALUATION
- What can you infer from the company names about their activities?
- What products might they sell? What services might they provide?
- Are there industry classifications you can determine from naming patterns?

STEP 3: PATTERN RECOGNITION  
- Company name clues: Does the name suggest an industry? (e.g., "Construction", "Insurance", "Medical")
- Legal entity type: LLC, Corp, Inc - what business patterns do these suggest?
- Context from the case name: Does the dispute suggest business types?

STEP 4: LOGICAL REASONING
- If direct evidence is limited, what can you reasonably infer?
- What industries commonly have disputes like this?
- Are there business relationships that make sense between these parties?

STEP 5: CLASSIFICATION
- Be SPECIFIC: "Commercial HVAC Contractor" not "Construction"
- Be DESCRIPTIVE: "Property & Casualty Insurance" not "Insurance"  
- Be ACCURATE: Base on evidence, mark uncertainty if needed

BROAD CATEGORIES (choose from): {broad_categories}

REASONING CHAIN:
For each company, walk through your thinking:
1. "I found evidence that [company] does [specific activities]"
2. "This suggests they operate in [specific industry]"  
3. "The broad category that best fits is [category]"
4. "My confidence level is [High/Medium/Low] because [reasoning]"

If you cannot find sufficient evidence despite thorough searching:
- Explain what you searched for
- Note what clues you tried to use
- Make your best educated inference with low confidence
- Use "Unknown" only as a last resort

OUTPUT FORMAT:
{{
    "plaintiff_industry": "Specific industry description",
    "plaintiff_industry_broad": "Broad category from list above",
    "defendant_industry": "Specific industry description", 
    "defendant_industry_broad": "Broad category from list above",
    "reasoning_summary": "Step-by-step explanation of your reasoning process and key insights",
    "confidence_level": "High/Medium/Low based on evidence quality", 
    "reasoning_approach": "What reasoning strategies you used to determine industries"
}}

Remember: Your job is to THINK THROUGH the problem, not give up with "Unknown"!
"""

class ResponseStatus(Enum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"

class IndustryReasoningAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1/chat/completions"  # Changed from /responses
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Conservative session setup
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def reason_about_industries(self, case_data: Dict, timeout_minutes: int = 5) -> Dict:
        """Use o3-mini reasoning model to classify industries via Chat Completions API."""
        
        case_name = case_data['case_name']
        plaintiff = case_data['plaintiff'] 
        defendant = case_data['defendant']
        original_row = case_data['original_row']
        
        # Build the reasoning prompt
        prompt = INDUSTRY_REASONING_PROMPT.format(
            case_name=case_name,
            plaintiff=plaintiff,
            defendant=defendant,
            broad_categories=", ".join(BROAD_CATEGORIES)
        )
        
        # Try up to 3 times for empty responses (reasoning model can be inconsistent)
        max_retries = 2
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"    🔄 Retry attempt {attempt}/{max_retries} for empty response...")
                time.sleep(5 + random.uniform(0, 3))  # Wait before retry
        
            # Build the reasoning prompt - Chat Completions API format
            payload = {
                "model": "o3-mini",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 2000,
                "reasoning_effort": "medium"  # o3-mini specific parameter (no temperature!)
            }
        
            try:
                print(f"  🧠 Sending to reasoning model (o3-mini via Chat Completions)...")
                
                # Make API request with longer timeout and more robust error handling
                response = self.session.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=180  # Increased timeout for reasoning model
                )
                
                if response.status_code != 200:
                    raise Exception(f"API error: {response.status_code} - {response.text}")
                
                result = response.json()
                print(f"    📊 Raw API response received: {len(str(result))} characters")
                
                # Extract content from Chat Completions format with detailed debugging
                if 'choices' not in result:
                    print(f"    ⚠️ No 'choices' in response: {result}")
                    raise ValueError("No choices in API response")
                    
                if len(result['choices']) == 0:
                    print(f"    ⚠️ Empty choices array: {result}")
                    raise ValueError("Empty choices array")
                    
                message = result['choices'][0].get('message', {})
                content = message.get('content', '')
                
                print(f"    📝 Content extracted: {len(content)} characters")
                
                if not content or content.strip() == "":
                    print(f"    ⚠️ Empty content in message: {message}")
                    print(f"    🔍 Full response for debugging: {result}")
                    raise ValueError("Empty response content - API returned blank")
                
                print(f"    ✅ Content preview: {content[:100]}...")
                
                # Rest of the processing...
                
                # Clean and parse JSON - More robust approach
                content = content.strip()
                
                # Remove markdown formatting
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                # Find JSON object boundaries
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                
                if json_start == -1 or json_end <= json_start:
                    # No JSON found, try to extract key info from text
                    print(f"  ⚠️ No JSON found, attempting text extraction...")
                    return self.extract_from_text(content, case_name, plaintiff, defendant, original_row)
                
                json_content = content[json_start:json_end]
                
                # Try to fix common JSON issues
                json_content = self.fix_common_json_issues(json_content)
                
                # Parse JSON with error handling
                try:
                    reasoning_result = json.loads(json_content)
                    print(f"    ✅ JSON parsed successfully")
                    break  # Success - exit retry loop
                    
                except json.JSONDecodeError as e:
                    print(f"    ⚠️ JSON parse failed: {str(e)[:50]}")
                    if attempt < max_retries:
                        print(f"    🔄 Will retry due to JSON parse error...")
                        continue  # Try again
                    else:
                        print(f"    ⚠️ All retries failed, using text extraction...")
                        return self.extract_from_text(content, case_name, plaintiff, defendant, original_row)

                # Update the original row with new industry information
                updated_row = original_row.copy()
                updated_row.update({
                    "Plaintiff Industry": reasoning_result.get("plaintiff_industry", "Unknown"),
                    "Plaintiff Industry (Broad)": reasoning_result.get("plaintiff_industry_broad", "Other"),
                    "Defendant Industry": reasoning_result.get("defendant_industry", "Unknown"), 
                    "Defendant Industry (Broad)": reasoning_result.get("defendant_industry_broad", "Other"),
                    "Status": f"Reasoned - {reasoning_result.get('confidence_level', 'Unknown')} confidence"
                })
                
                confidence = reasoning_result.get('confidence_level', 'Unknown')
                print(f"  ✅ Industries classified: {confidence} confidence")
                if confidence == 'Low':
                    reasoning_approach = reasoning_result.get('reasoning_approach', 'N/A')[:100]
                    print(f"     Approach: {reasoning_approach}...")
                
                return updated_row

            except Exception as e:
                print(f"    ❌ API error on attempt {attempt + 1}: {str(e)[:100]}")
                if attempt < max_retries:
                    print(f"    🔄 Will retry due to API error...")
                    continue  # Try again
                else:
                    print(f"    ❌ All retries failed")
                    # Return original row with error status
                    error_row = original_row.copy()
                    error_row["Status"] = f"All retries failed: {str(e)[:100]}"
                    return error_row
    
    def fix_common_json_issues(self, json_str: str) -> str:
        """Fix common JSON formatting issues."""
        try:
            # Fix unterminated strings by ensuring proper quotes
            lines = json_str.split('\n')
            fixed_lines = []
            
            for line in lines:
                # Fix lines that might have unterminated strings
                if line.strip().endswith('"') and line.count('"') % 2 == 1:
                    line = line.rstrip('"') + '"'
                elif '"' in line and line.count('"') % 2 == 1 and not line.strip().endswith(','):
                    line = line + '"'
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
        except:
            return json_str
    
    def extract_from_text(self, content: str, case_name: str, plaintiff: str, defendant: str, original_row: dict) -> dict:
        """Extract industry info from text when JSON parsing fails."""
        print(f"  🔍 Extracting from text content...")
        
        # Try to find industry mentions in the text
        content_lower = content.lower()
        
        # Common industry keywords to look for
        industry_keywords = {
            'construction': ('Construction', 'Construction'),
            'insurance': ('Insurance', 'Insurance'), 
            'technology': ('Software/Technology', 'Technology'),
            'healthcare': ('Healthcare', 'Healthcare'),
            'manufacturing': ('Manufacturing', 'Manufacturing'),
            'real estate': ('Real Estate', 'Real Estate'),
            'financial': ('Financial Services', 'Financial Services'),
            'legal': ('Legal Services', 'Professional Services'),
            'consulting': ('Business Consulting', 'Professional Services'),
            'transportation': ('Transportation', 'Transportation'),
            'retail': ('Retail', 'Retail'),
            'energy': ('Energy', 'Energy')
        }
        
        plaintiff_industry = "Unknown"
        plaintiff_broad = "Other"
        defendant_industry = "Unknown" 
        defendant_broad = "Other"
        confidence = "Low"
        
        # Look for industry keywords in the content
        for keyword, (specific, broad) in industry_keywords.items():
            if keyword in content_lower:
                if plaintiff_industry == "Unknown":
                    plaintiff_industry = specific
                    plaintiff_broad = broad
                elif defendant_industry == "Unknown":
                    defendant_industry = specific
                    defendant_broad = broad
                confidence = "Medium"
        
        # Update row
        updated_row = original_row.copy()
        updated_row.update({
            "Plaintiff Industry": plaintiff_industry,
            "Plaintiff Industry (Broad)": plaintiff_broad,
            "Defendant Industry": defendant_industry,
            "Defendant Industry (Broad)": defendant_broad,
            "Status": f"Text extracted - {confidence} confidence"
        })
        
        print(f"  ✅ Text extraction complete: {confidence} confidence")
        return updated_row

def load_cases_from_csv(filename: str) -> List[Dict]:
    """Load cases that need industry classification from CSV/Excel."""
    try:
        # Try Excel first, then CSV
        if filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(filename)
        else:
            df = pd.read_csv(filename)
        
        print(f"✓ Loaded {len(df)} cases from {filename}")
        print(f"✓ Columns found: {list(df.columns)}")
        
        # Filter for cases with "Unknown" in industry fields (using your exact field names)
        unknown_cases = df[
            (df.get('Plaintiff Industry', '') == 'Unknown') | 
            (df.get('Defendant Industry', '') == 'Unknown') |
            (df.get('Plaintiff Industry', '').isna()) |
            (df.get('Defendant Industry', '').isna()) |
            (df.get('Plaintiff Industry', '') == '') |
            (df.get('Defendant Industry', '') == '')
        ]
        
        print(f"✓ Found {len(unknown_cases)} cases with unknown industries")
        
        # Convert to list of dicts with your exact field names
        cases = []
        for _, row in unknown_cases.iterrows():
            case_name = str(row.get('Case Name', '')).strip()
            plaintiff = str(row.get('Plaintiff(s)', '')).strip()
            defendant = str(row.get('Defendant(s)', '')).strip()
            
            if case_name and plaintiff and defendant:
                cases.append({
                    'case_name': case_name,
                    'plaintiff': plaintiff,
                    'defendant': defendant,
                    'original_row': row.to_dict()  # Keep original data for reference
                })
        
        print(f"✓ Prepared {len(cases)} cases for industry reasoning")
        return cases
        
    except Exception as e:
        print(f"❌ Error loading cases: {e}")
        return []

def process_case_batch(case_batch: List[Dict], api_key: str) -> List[Dict]:
    """Process a batch of cases with reasoning."""
    api_client = IndustryReasoningAPI(api_key)
    results = []
    
    for case_data in case_batch:
        try:
            result = api_client.reason_about_industries(case_data, timeout_minutes=5)  # Longer for reasoning
            results.append(result)
        except Exception as e:
            print(f"  ❌ Batch error for {case_data['case_name']}: {e}")
            error_row = case_data['original_row'].copy()
            error_row["Status"] = f"Batch error: {str(e)[:100]}"
            results.append(error_row)
        
        # Small delay between cases in batch
        time.sleep(random.uniform(1, 2))
    
    return results

def run_industry_reasoning_sequential(input_file: str, output_file: str = "Industry_Reasoned_Results.xlsx"):
    """Main function to run industry reasoning on unknown cases."""
    
    print("🧠 INDUSTRY REASONING SCRIPT")
    print("="*50)
    
    # Load API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Try loading from your new file path
        try:
            with open(r"C:\Users\HannahRose_x3m0sef\OneDrive - Qi Venture Partners\Open AI Api\Case Research\Case Research Hannah API KEy.txt", 'r') as f:
                api_key = f.read().strip()
        except:
            # Fallback: look in current directory
            try:
                with open("Case Research Hannah API KEy.txt", 'r') as f:
                    api_key = f.read().strip()
            except:
                print("❌ Could not find API key file")
                print("   Please set OPENAI_API_KEY environment variable")
                print("   Or put 'Case Research Hannah API KEy.txt' in current directory")
                return
    
    # Load cases
    cases = load_cases_from_csv(input_file)
    if not cases:
        print("❌ No cases to process")
        return
    
    total_cases = len(cases)  # Define total_cases here
    
    # Initialize API client
    print(f"\n🚀 Initializing reasoning API client...")
    api_client = IndustryReasoningAPI(api_key)
    
    # Test connection
    print("🔌 Testing API connection...")
    try:
        # Simple test with Chat Completions API format
        test_payload = {
            "model": "o3-mini",
            "messages": [
                {"role": "user", "content": "Test connection: respond with just 'Connection OK'"}
            ],
            "max_completion_tokens": 10
        }
        
        response = api_client.session.post(
            api_client.base_url,
            headers=api_client.headers,
            json=test_payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                print("✅ API connection successful!")
            else:
                raise Exception("No response content")
        else:
            raise Exception(f"API test failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return
    
    # Process cases sequentially (more reliable than parallel)
    print(f"\n📊 Processing {total_cases} cases sequentially with reasoning...")
    print(f"   Model: o3-mini (reasoning model via Chat Completions)")
    print(f"   Note: Using model knowledge + reasoning (no web search)")
    print(f"⏰ Estimated time: {total_cases * 1.0:.0f} minutes ({total_cases * 1.0 / 60:.1f} hours)")
    print(f"   (Sequential processing - more reliable)")
    
    confirm = input(f"\nProceed with sequential reasoning analysis? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Cancelled")
        return
    
    # Process cases one by one
    start_time = datetime.now()
    all_results = []
    
    for i, case_data in enumerate(cases, 1):
        print(f"\n📋 Case {i}/{total_cases}: {case_data['case_name']}")
        
        try:
            result = api_client.reason_about_industries(case_data, timeout_minutes=5)
            all_results.append(result)
        except Exception as e:
            print(f"  ❌ Case processing error: {e}")
            error_row = case_data['original_row'].copy()
            error_row["Status"] = f"Processing error: {str(e)[:100]}"
            all_results.append(error_row)
        
        # Progress update
        if i % 2 == 0 or i == total_cases:
            elapsed = datetime.now() - start_time
            rate = i / elapsed.total_seconds() * 60  # cases per minute
            remaining_cases = total_cases - i
            eta_minutes = remaining_cases / rate if rate > 0 else 0
            
            print(f"\n📈 Progress: {i}/{total_cases} ({i/total_cases*100:.1f}%)")
            if i > 0:
                print(f"   Rate: {rate:.1f} cases/minute")
                print(f"   ETA: {eta_minutes:.1f} minutes")
        
        # Small delay between cases (be kind to API)
        if i < total_cases:
            time.sleep(random.uniform(2, 4))
    
    # Save results with original column order
    print(f"\n💾 Saving results to {output_file}...")
    
    # Use original column structure
    if all_results:
        df = pd.DataFrame(all_results, columns=ORIGINAL_COLUMNS)
        df.to_excel(output_file, index=False)
    
    # Summary
    duration = datetime.now() - start_time
    successful = sum(1 for r in all_results if "error" not in r.get("Status", "").lower() and "failed" not in r.get("Status", "").lower())
    
    print(f"\n✅ SEQUENTIAL REASONING COMPLETE!")
    print(f"📁 Output: {output_file}")
    print(f"📊 Processed: {total_cases} cases")
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {total_cases - successful}")
    print(f"⏰ Duration: {duration.total_seconds()/60:.1f} minutes")
    print(f"🚀 Rate: {total_cases / (duration.total_seconds()/60):.1f} cases/minute")
    print(f"🧠 Model used: o3-mini (reasoning via Chat Completions API - sequential processing)")

if __name__ == "__main__":
    # USAGE: 
    # 1. Make sure "Industry Unkowns.xlsx" is in the same folder as this script
    # 2. Run the script
    # 3. It will find cases with "Unknown" industries and reason about them
    # 4. Output preserves all original columns, just updates the industry fields
    
    INPUT_FILE = "Industry Unkowns.xlsx"           # Your file with unknown industries
    OUTPUT_FILE = "Industry_Reasoned_Results.xlsx"  # Updated results with reasoning
    
    # SEQUENTIAL PROCESSING (more reliable):
    # Processes cases one by one to avoid parallel processing issues
    
    run_industry_reasoning_sequential(
        input_file=INPUT_FILE, 
        output_file=OUTPUT_FILE
    )