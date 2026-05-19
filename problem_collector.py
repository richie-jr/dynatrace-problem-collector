"""
+-----------------------------------------------------------------------+
|  SCRIPT NAME     : Dynatrace Problem Collector (Optimized)            |
|  OWNED BY        : PT ISGS (Division: BROS)                           |
|  ORIGINAL AUTHOR : Richie J.S                                         |
|  MAINTAINED BY   : -                                                  |
|  VERSION         : 2.0 (Native API & Excel Export)                    |
|  DESCRIPTION     : Automated problem fetching and translation.        |
+-----------------------------------------------------------------------+
"""

import os
import re
import json
import configparser
from datetime import datetime
from dynatrace import Dynatrace
import pandas as pd

def print_banner():
    banner = r"""====================================================================
      ___                  _                      
     |   \ _  _ _ _  __ _ | |_ _ _ __ _ __ ___ 
     | |) | || | ' \/ _` |  _| '_/ _` / _/ -_)
     |___/ \_, |_||_\__,_|\__|_| \__,_\__\___|
           |__/          >> PROBLEM COLLECTOR v2.0 <<
           
    OWNED BY : PT ISGS - BROS - R.J.S
===================================================================="""
    print(banner)

# --- CONFIGURATION LOADER ---
def load_config():
    config = configparser.ConfigParser()
    config_file = 'config.ini'
    
    if not os.path.exists(config_file):
        print(f"\n [!] Config file not found. Generating '{config_file}' template...")
        config['DYNATRACE'] = {
            'base_url': 'https://your-environment-id.live.dynatrace.com',
            'api_token': 'your-api-token-here',
            'max_workers': '10' # Kept so your existing config file doesn't break
        }
        with open(config_file, 'w') as f:
            config.write(f)
        print(f" [!] Please edit '{config_file}' and restart.")
        input("\n Press Enter to exit...")
        exit()
    
    config.read(config_file)
    try:
        url = config['DYNATRACE']['base_url'].strip('/')
        token = config['DYNATRACE']['api_token']
        return url, token
    except KeyError as e:
        print(f" [❌] Error in config.ini: Missing {e}")
        input("\n Press Enter to exit...")
        exit()

def translate_text(text):
    patterns = {
        r"The Memory used % value was above normal behavior": "Memori yang digunakan % berada di atas perilaku normal.",
        r"The CPU usage % value was above normal behavior": "Nilai % penggunaan CPU berada di atas perilaku normal.",
        r"The load increased to (\d+) requests/min": r"Load meningkat menjadi \1 permintaan/mnt.",
        r"Host or monitoring unavailable": "Host or monitoring tidak tersedia karena gangguan konektivitas/server.",
        r"Process\s([^()]+)\s\([^()]+\)\srestarted": r"Proses \1 dimulai ulang"
    }
    for pattern, replacement in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return '-'

def process_problems_natively(start_date, end_date, start_time, end_time, base_url, api_token):
    dt = Dynatrace(base_url, api_token)
    
    # We ask DT for everything up front to kill the N+1 problem
    fields = "+impactLevel,+managementZones,+evidenceDetails,+impactedEntities"
    
    start_iso = f"{start_date}T{start_time}"
    end_iso = f"{end_date}T{end_time}"
    
    # Fetching generator directly
    problems_iterator = dt.problems.list(
        time_from=f"{start_iso}:00.123+07:00",
        time_to=f"{end_iso}:59.123+07:00",
        fields=fields
    )

    results = []
    
    # Iterate natively. The client handles pagination in the background.
    for prob in problems_iterator:
        # 1. They are already datetime objects! No conversion needed.
        start_dt = prob.start_time
        end_dt = prob.end_time # This will be None if the problem is still open

        prob_date_str = start_dt.strftime('%Y-%m-%d')
        prob_time_str = start_dt.strftime('%H:%M')

        # Strict boundary filtering
        if not (start_date <= prob_date_str <= end_date):
            continue
        if not (start_time <= prob_time_str <= end_time):
            continue

        # 2. Duration Calculation using native Python timedelta
        if not end_dt:
            duration_text = "-"
        else:
            # Subtracting two datetimes gives a 'timedelta' object natively
            duration = end_dt - start_dt 
            
            days = duration.days
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            duration_text = f"{days} days {hours} hours {minutes} minutes"

        # Safe extraction of nested data
        mz_name = prob.management_zones[0].name if prob.management_zones else "-"
        impacted = prob.impacted_entities[0].name if prob.impacted_entities else "-"
        
        error_original = "-"
        if prob.evidence_details and prob.evidence_details.details:
            for ev in prob.evidence_details.details:
                if getattr(ev, 'evidence_type', None) == 'EVENT':
                    # Use getattr to dynamically fetch 'data' to satisfy Pylance
                    ev_data = getattr(ev, 'data', None)
                    if ev_data and getattr(ev_data, 'properties', None):
                        for p in ev_data.properties:
                            if getattr(p, 'key', None) == 'dt.event.description':
                                error_original = getattr(p, 'value', '-').replace('\n', ' ')

        # Use getattr to safely extract Enum values without triggering type warnings
        impact_level = str(getattr(prob.impact_level, 'value', prob.impact_level))
        status = str(getattr(prob.status, 'value', prob.status))

        results.append({
            "No": len(results) + 1,
            "Problem ID": prob.display_id,
            "Date": prob_date_str,
            "Issues": prob.title,
            "Problem Category": impact_level,
            "Application": mz_name,
            "Host/Service": impacted,
            "Error Original": error_original,
            "Error Message": translate_text(error_original),
            "Timestamp": start_dt.strftime('%Y-%m-%d %H:%M'),
            "Time Resolved": end_dt.strftime('%Y-%m-%d %H:%M') if end_dt else "-",
            "Duration": duration_text,
            "Status": status,
            "URL": f"{base_url}/#problems/problemdetails;gf=all;pid={prob.problem_id}"
        })

    return results

def run_shell_gui():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')

        BASE_URL, API_TOKEN = load_config()

        print_banner()
        # --- 1. CONFIGURATION INPUTS ---
        today = datetime.now().strftime('%Y-%m-%d')
        print(" 📅 RANGE SETTINGS")
        start_date = input(f"  > Start Date (YYYY-MM-DD) [{today}]: ".ljust(45)) or today
        start_time = input(f"  > Start Time (HH:mm)      [00:00]: ".ljust(45)) or "00:00"
        end_date   = input(f"  > End Date   (YYYY-MM-DD) [{start_date}]: ".ljust(45)) or start_date
        end_time   = input(f"  > End Time   (HH:mm)      [23:59]: ".ljust(45)) or "23:59"

        print("\n 📂 FORMAT SELECTION")
        print("  [1] Excel (.xlsx format)")
        print("  [2] JSON (.json format)")
        choice = input("  > Choice [1]: ") or "1"
        
        # --- 2. Processing ---
        try:
            print(f"\n 🚀 PROCESSING")
            # Combined Fetching and Processing into 1 step
            print(f"  [1/2] 🔍 Requesting & processing natively from Dynatrace...")
            
            results = process_problems_natively(start_date, end_date, start_time, end_time, BASE_URL, API_TOKEN)

            if not results:
                print("      ❌ No problems found for this time range.")
                print("\n SELECT TO CONTINUE")
                choice_restart = input(" [1] Restart | [2] Exit: ").strip()
                if choice_restart == "1":
                    continue
                else:
                    break

            print("  [2/2] 💾 Generating file...")
            base_filename = f"problems_{start_date}_{start_time.replace(':', '')}_to_{end_date}_{end_time.replace(':', '')}"
            
            if choice == "2":
                final_name = f"{base_filename}.json"
                with open(final_name, 'w') as f:
                    json.dump(results, f, indent=4)
            else:
                final_name = f"{base_filename}.xlsx"
                # The Magic of Pandas: Turn dictionaries directly into an Excel File
                df = pd.DataFrame(results)
                df.to_excel(final_name, index=False)
            
            print(f"\n ✨ SUCCESS: Saved as {final_name}")
            print("="*68)
            choice_end = input("\n [1] Restart | [2] Exit: ").strip()
            
            if choice_end == "1":
                continue 
            else:
                break

        except Exception as e:
            print(f"\n ❌ SYSTEM ERROR: {e}")
            print(f" ⚠️ PLEASE CHECK YOUR CONFIGURATION AND NETWORK CONNECTION.")
            input(" Press Enter to exit...")

if __name__ == "__main__":
    run_shell_gui()