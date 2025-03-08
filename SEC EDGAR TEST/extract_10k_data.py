import os
import requests
import pymysql
import time
import webbrowser
import tempfile
from datetime import datetime



# SEC API Base URL
SEC_API_BASE = "https://www.sec.gov"

# Required Headers
HEADERS = {
    "User-Agent": "jackbian0903@gmail.com"
}

# Database Credentials
DB_HOST = "siai-financial-data.cds66i4yidxk.us-east-2.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "123321123"
DB_NAME = "siai_financial_data"

def get_cik_from_ticker(ticker: str):
    """ Retrieves the CIK number from the ticker symbol. """
    ticker = ticker.upper()
    cik_url = "https://www.sec.gov/files/company_tickers.json"
    try:
        response = requests.get(cik_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        cik_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching CIK data: {e}")
        return None
    for entry in cik_data.values():
        if entry["ticker"] == ticker:
            cik = str(entry["cik_str"]).zfill(10)
            print(f"✅ Found CIK for {ticker}: {cik}")
            return cik
    print(f"⚠️ No CIK found for ticker {ticker}")
    return None


def check_filing_in_db(filing_key):
    """ Checks if the filing exists in the database and optionally displays it in a browser. """
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT file_content FROM sec_filings WHERE filing_key = %s", (filing_key,))
        result = cursor.fetchone()

        conn.close()

        if result:
            print(f"✅ Filing found in database for {filing_key}. No need to fetch from API.")

            # Ask user if they want to open the file in the browser
            choice = input("Would you like to display the HTML file in a browser? (y/n): ").strip().lower()

            if choice == "y":
                # Create a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as temp_file:
                    temp_file.write(result[0])  # Write HTML content
                    temp_path = temp_file.name  # Get the file path

                # Open the HTML file in the default web browser
                webbrowser.open(f"file://{temp_path}")
                print(f"🌍 Opening {filing_key} in browser...")

            return result[0]  # Returns the stored HTML content
        else:
            print(f"❌ Filing not found in database: {filing_key}")
            return None

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None


def fetch_and_store_filing(cik, ticker, year, form_type):
    """ Fetches the filing from SEC, stores it in the database, and optionally opens it in the browser. """
    filings_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    try:
        response = requests.get(filings_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error for {ticker}: {e}")
        return None

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})

    for i, form in enumerate(filings.get("form", [])):
        filing_date = filings.get("filingDate", [])[i]
        filing_year = int(filing_date.split("-")[0]) if filing_date else None

        if form == form_type and filing_year == year:
            accession_number = filings["accessionNumber"][i].replace("-", "")
            primary_doc = filings["primaryDocument"][i]
            filing_url = f"{SEC_API_BASE}/Archives/edgar/data/{cik}/{accession_number}/{primary_doc}"

            try:
                response = requests.get(filing_url, headers=HEADERS, timeout=15)
                response.raise_for_status()
                html_content = response.text  # Fetch actual HTML content

                # Determine filing key
                filing_key = f"{ticker}_{year}" if form_type == "10-K" else f"{ticker}_{year}_{i+1}"

                # Store in DB
                store_filing_in_db(filing_key, ticker, year, form_type, html_content)

                print(f"✅ {form_type} filing for {ticker} saved in DB")

                # Ask user if they want to open the file in the browser
                choice = input("Would you like to display the newly stored HTML file in a browser? (y/n): ").strip().lower()
                if choice == "y":
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as temp_file:
                        temp_file.write(html_content)  # Write HTML content
                        temp_path = temp_file.name  # Get the file path

                    # Open the HTML file in the default web browser
                    webbrowser.open(f"file://{temp_path}")
                    print(f"🌍 Opening {filing_key} in browser...")

                return html_content  # Return the stored HTML content

            except requests.exceptions.RequestException as e:
                print(f"❌ Error fetching {form_type} for {ticker}: {e}")
                return None

    print(f"⚠️ No {form_type} filing found for {ticker} ({cik}) in {year}.")
    return None



def store_filing_in_db(filing_key, company, year, filing_type, file_content):
    """ Stores the fetched SEC filing in the database. """
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sec_filings (filing_key, company, year, filing_type, file_content)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE file_content = VALUES(file_content)
            """,
            (filing_key, company, year, filing_type, file_content)
        )
        conn.commit()
        conn.close()
        print(f"✅ Filing stored successfully in database: {filing_key}")
    except Exception as e:
        print(f"❌ Error storing filing in database: {e}")

def validate_user_input():
    """Ensures the user enters a valid year and a properly formatted form type."""
    current_year = datetime.now().year

    while True:
        try:
            year = int(input("Enter the filing year (e.g., 2023): ").strip())

            # Check for incorrect years like 20221
            if year < 1995 or year > current_year:
                print(f"⚠️ Invalid year: {year}. Please enter a valid year (1995 - {current_year}).")
                continue  # Ask again

            break  # Valid year, exit loop

        except ValueError:
            print("⚠️ Please enter a valid numeric year.")
    
    while True:
        form_type = input("Enter the form type (10-K or 10-Q): ").strip().upper()

        # Normalize variations of 10-K and 10-Q
        if form_type in ["10K", "10-K", "10k"]:
            form_type = "10-K"
        elif form_type in ["10Q", "10-Q", "10q"]:
            form_type = "10-Q"
        else:
            print("⚠️ Invalid form type. Please enter '10-K' or '10-Q'.")
            continue  # Ask again
        
        break  # Valid form type, exit loop

    return year, form_type

def main():
    """ Main function to check SEC filings in the DB before fetching. """
    while True:
        try:
            company_input = input("Enter the company ticker or CIK: ").strip().upper()
            year, form_type = validate_user_input()  # Get validated input

            cik = company_input if company_input.isdigit() else get_cik_from_ticker(company_input)

            if not cik:
                print("⚠️ Unable to determine CIK. Please enter a valid ticker or CIK.")
                continue

            filing_key = f"{company_input}_{year}" if form_type == "10-K" else f"{company_input}_{year}_1"

            # Check DB first
            existing_filing = check_filing_in_db(filing_key)

            if existing_filing:
                print(f"📄 Retrieved filing from DB:\n{existing_filing[:500]}...")  # Show preview
            else:
                print(f"🔍 Fetching filing from SEC API...")
                new_filing = fetch_and_store_filing(cik, company_input, year, form_type)
                if new_filing:
                    print(f"📄 Retrieved newly stored filing:\n{new_filing[:500]}...")  # Show preview

            break  # Exit loop if successful

        except ValueError:
            print("⚠️ Unexpected error. Please try again.")

if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
