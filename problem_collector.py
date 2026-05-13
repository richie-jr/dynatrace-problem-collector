"""
+-----------------------------------------------------------------------+
|  SCRIPT NAME     : Dynatrace Problem Collector                        |
|  OWNED BY        : PT ISGS (Division: BROS)                           |
|  ORIGINAL AUTHOR : Richie J.S                                         |
|  MAINTAINED BY   : -                                                  |
|  VERSION         : 1.0                                                |
|  DESCRIPTION     : Automated problem fetching and translation.        |
+-----------------------------------------------------------------------+
"""

import requests
import json
import re
import csv
import os
import configparser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

def print_banner():
    banner = r"""====================================================================
      ___                  _                      
     |   \ _  _ _ _  __ _ | |_ _ _ __ _ __ ___ 
     | |) | || | ' \/ _` |  _| '_/ _` / _/ -_)
     |___/ \_, |_||_\__,_|\__|_| \__,_\__\___|
           |__/          >> PROBLEM COLLECTOR v1.0 <<
           
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
            'max_workers': '10'
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
        # Read max_workers as an integer, defaulting to 10 if not found
        workers = int(config['DYNATRACE'].get('max_workers', 10))
        return url, token, workers
    except (KeyError, ValueError) as e:
        print(f" [❌] Error in config.ini: {e}")
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

def fetch_problems(start_iso, end_iso, base_url, headers):
    all_problems = []
    url = f"{base_url}/api/v2/problems"
    params = {
        "from": f"{start_iso}:00.123+07:00",
        "to": f"{end_iso}:59.123+07:00",
        "sort": "+startTime",
        "pageSize": 500
    }
    while True:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        all_problems.extend(data.get('problems', []))
        next_key = data.get('nextPageKey')
        if next_key:
            params = {"nextPageKey": next_key}
        else:
            break
    return all_problems

def fetch_single_detail(prob, base_url, headers):
    prob_id = prob['problemId']
    try:
        detail_url = f"{base_url}/api/v2/problems/{prob_id}"
        resp = requests.get(detail_url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        start_dt = datetime.fromtimestamp(data.get('startTime', 0) / 1000.0)
        end_dt = datetime.fromtimestamp(data.get('endTime', 0) / 1000.0) if data.get('endTime') else None
        
        start_time_ms = data.get('startTime', 0)
        end_time_ms = data.get('endTime', -1)
        
        if end_time_ms == -1:
            duration_text = "-"
        else:
            duration_ms = end_time_ms - start_time_ms
            minutes_duration = (duration_ms // (1000 * 60)) % 60
            hours_duration = (duration_ms // (1000 * 60 * 60)) % 24
            days_duration = duration_ms // (1000 * 60 * 60 * 24)
            duration_text = f"{days_duration} days {hours_duration} hours {minutes_duration} minutes"

        impacted_list = data.get('impactedEntities', [])
        impacted = impacted_list[0].get('name', '-') if impacted_list else "-"
        impact_level = data.get('impactLevel', '-')
        
        mz_list = data.get('managementZones', [])
        mz_name = mz_list[0].get('name', '-') if mz_list else "-"
        
        error_original = "-"
        evidence = data.get('evidenceDetails', {}).get('details', [])
        for ev in evidence:
            if ev.get('evidenceType') == 'EVENT':
                properties = ev.get('data', {}).get('properties', [])
                for p in properties:
                    if p.get('key') == 'dt.event.description':
                        error_original = p.get('value', '-').replace('\n', ' ')

        return {
            "Problem ID": data.get('displayId', '-'),
            "Date": start_dt.strftime('%Y-%m-%d'),
            "Issues": data.get('title', '-'),
            "Problem Category": impact_level,
            "Application": mz_name,
            "Host/Service": impacted,
            "Error Original": error_original,
            "Error Message": translate_text(error_original),
            "Timestamp": start_dt.strftime('%Y-%m-%d %H:%M'),
            "Time Resolved": end_dt.strftime('%Y-%m-%d %H:%M') if end_dt else "-",
            "Duration": duration_text,
            "Status": data.get('status', '-'),
            "URL": f"{base_url}/#problems/problemdetails;gf=all;pid={prob_id}"
        }
    except Exception as e:
        return None

def process_details(problems, start_date, end_date, start_time, end_time, base_url, headers, max_workers):
    results = []
    total = len(problems)
    
    # max_workers = max_threads. Don't go too high or API Limit might block.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        mapped_function = lambda prob: fetch_single_detail(prob, base_url, headers)
        for i, result in enumerate(executor.map(mapped_function, problems)):
            if result:
                if start_date <= result["Date"] <= end_date:
                    if start_time <= result["Timestamp"].split()[-1] <= end_time:
                        result = {"No": len(results) + 1, **result}
                        results.append(result)
            print(f"\r      ⚡ Progress: {i+1}/{total} analyzed", end="")
            
    print(f"\n      ✅ Processing complete. ({len(results)} filtered items kept)")
    return results

def run_shell_gui():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')

        # Load credentials at startup
        BASE_URL, API_TOKEN, MAX_WORKERS = load_config()
        HEADERS = {
            "Authorization": f"Api-Token {API_TOKEN}",
            "Content-Type": "application/json"
        }

        print_banner()
        # --- 1. CONFIGURATION INPUTS ---
        today = datetime.now().strftime('%Y-%m-%d')
        print(" 📅 RANGE SETTINGS")
        start_date = input(f"  > Start Date (YYYY-MM-DD) [{today}]: ".ljust(45)) or today
        start_time = input(f"  > Start Time (HH:mm)      [00:00]: ".ljust(45)) or "00:00"
        end_date   = input(f"  > End Date   (YYYY-MM-DD) [{start_date}]: ".ljust(45)) or start_date
        end_time   = input(f"  > End Time   (HH:mm)      [23:59]: ".ljust(45)) or "23:59"

        print("\n 📂 FORMAT SELECTION")
        print("  [1] CSV (Excel Friendly)")
        print("  [2] JSON (Data format)")
        choice = input("  > Choice [1]: ") or "1"
        
        start_iso = f"{start_date}T{start_time}"
        end_iso = f"{end_date}T{end_time}"
        
        # --- 2. Processing ---
        try:
            print(f"\n 🚀 PROCESSING")
            print(f"  [1/3] 🔍 Requesting data from Dynatrace...")
            problems = fetch_problems(start_iso, end_iso, BASE_URL, HEADERS)
            
            if not problems:

                print("      ❌ No problems found for this time range.")
                print("\n SELECT TO CONTINUE")
                choice = input(" [1] Restart | [2] Exit: ").strip()
                if choice == "1":
                    continue
                else:
                    break

            print(f"  [2/3] ⚙️  Processing {len(problems)} problem details...")
            results = process_details(problems, start_date, end_date, start_time, end_time, BASE_URL, HEADERS, MAX_WORKERS)

            if not results:
                print("      ❌ No problems found for this time range.")
                print("\n SELECT TO CONTINUE")
                choice = input(" [1] Restart | [2] Exit: ").strip()
                if choice == "1":
                    continue
                else:
                    break

            print("  [3/3] 💾 Generating file...")
            base_filename = f"problems_{start_date}_{start_time.replace(':', '')}_to_{end_date}_{end_time.replace(':', '')}"
            
            if choice == "2":
                final_name = f"{base_filename}.json"
                with open(final_name, 'w') as f:
                    json.dump(results, f, indent=4)
            else:
                final_name = f"{base_filename}.csv"
                with open(final_name, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=results[0].keys())
                    writer.writeheader()
                    writer.writerows(results)
            
            print(f"\n ✨ SUCCESS: Saved as {final_name}")
            print("="*68)
            choice = input("\n [1] Restart | [2] Exit: ").strip()
            
            if choice == "1":
                continue 
            else:
                break

        except Exception as e:
            print(f"\n ❌ SYSTEM ERROR: {e}")
            print(f" ⚠️ PLEASE CHECK YOUR CONFIGURATION AND NETWORK CONNECTION.")
            input(" Press Enter to exit...")

if __name__ == "__main__":
    run_shell_gui()