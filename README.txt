===========================================================
DYNATRACE PROBLEM COLLECTOR - DOCUMENTATION
===========================================================

DESCRIPTION:
This tool fetches problem data from Dynatrace via API and 
exports the results to CSV or JSON for reporting.

-----------------------------------------------------------
1. PREREQUISITES
-----------------------------------------------------------
- Python 3.8 or higher.
- A Dynatrace API Token with the following permission:
  - Read problems (problems.read)

-----------------------------------------------------------
2. SETUP VIRTUAL ENVIRONMENT (VENV)
-----------------------------------------------------------
Open your terminal in the project folder and run:

FOR WINDOWS:
Step A: python -m venv venv
Step B: .\venv\Scripts\activate

FOR MAC/LINUX:
Step A: python3 -m venv venv
Step B: source venv/bin/activate

-----------------------------------------------------------
3. INSTALL LIBRARIES
-----------------------------------------------------------
With your (venv) active, install the required 'requests' library:

pip install requests

OR

pip install -r requirements.txt

-----------------------------------------------------------
4. CONFIGURATION (config.ini)
-----------------------------------------------------------
The script now uses an external 'config.ini' file. On the 
first run, the script will generate a template for you.

- base_url: Your Dynatrace environment URL (e.g., https://abc12345.live.dynatrace.com)
- api_token: Your secret Dynatrace API Token.
- max_workers: The number of simultaneous threads (Default: 10). 
  Increase for faster downloads; decrease if you hit API limits / slow computer.

-----------------------------------------------------------
5. RUNNING THE SCRIPT
-----------------------------------------------------------
Run the collector using:

python problem_collector.py

The script will guide you through:
1. Entering the Date Range (Start and End).
2. Choosing the file format (CSV or JSON).
3. Viewing real-time progress as details are fetched.
4. Option to [1] Restart for a new range or [2] Exit.

-----------------------------------------------------------
6. TROUBLESHOOTING
-----------------------------------------------------------
- Config Error: If the script says "Config file not found," 
  it has created a blank one. Open 'config.ini' and fill 
  in your credentials.
- Missing Translations: If an error doesn't match a 
  predefined pattern, the script returns '-' by default.
- 0 Items Filtered: This happens if Dynatrace found 
  problems active in that window, but they actually 
  started BEFORE your selected Start Date.
===========================================================