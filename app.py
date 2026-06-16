import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app) 

mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("No MONGO_URI found in environment variables.")

client = MongoClient(mongo_uri)
db = client["StarQ"]

@app.route('/api/analysis', methods=['GET'])
def get_analysis():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({"error": "Start and end dates are required."}), 400

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Initialize data structures for all charts
    dashboard_data = {
        "revenue_by_distributor": {},
        "monthly_trend": {},
        "collections_vs_due": {"Collected": 0, "Due": 0},
        "subject_distribution": {"Maths": 0, "Physics": 0, "Chemistry": 0, "Botany": 0, "Zoology": 0, "Sanskrit": 0, "Other": 0},
        "top_books": {},
        "customer_revenue": {},
        "outstanding_dues": {}
    }

    for collection_name in db.list_collection_names():
        distributor = collection_name
        collection = db[collection_name]
        
        if distributor not in dashboard_data["revenue_by_distributor"]:
            dashboard_data["revenue_by_distributor"][distributor] = 0
        
        for doc in collection.find():
            customer = doc.get("Customer", "Unknown Customer")
            
            # Document-level stats (Snapshot, independent of date filter)
            dashboard_data["collections_vs_due"]["Collected"] += doc.get("Collection", 0)
            dashboard_data["collections_vs_due"]["Due"] += doc.get("Total_Due", 0)
            
            dashboard_data["outstanding_dues"][customer] = dashboard_data["outstanding_dues"].get(customer, 0) + doc.get("Total_Due", 0)
            
            # Transaction-level stats (Date filtered)
            for txn in doc.get("Transactions", []):
                txn_date_raw = txn.get("Date")
                if not txn_date_raw: continue
                
                try:
                    # Date Parsing Logic
                    if isinstance(txn_date_raw, datetime):
                        txn_date = txn_date_raw.replace(tzinfo=None) 
                    elif isinstance(txn_date_raw, dict) and "$date" in txn_date_raw:
                        date_val = txn_date_raw["$date"]
                        if isinstance(date_val, (int, float)): 
                            txn_date = datetime.fromtimestamp(date_val / 1000.0)
                        else:
                            txn_date = datetime.strptime(str(date_val)[:10], "%Y-%m-%d")
                    elif isinstance(txn_date_raw, str):
                        txn_date = datetime.strptime(txn_date_raw[:10], "%Y-%m-%d")
                    else: continue 
                        
                    if start_date <= txn_date <= end_date:
                        month_key = txn_date.strftime("%Y-%m") # e.g., "2025-07"
                        
                        for item in txn.get("Items", []):
                            title = item.get("Title", "Unknown")
                            net_copies = item.get("Net_Copies", 0)
                            amount = item.get("Amount", 0)

                            # 1. Revenue by Distributor & Customer
                            dashboard_data["revenue_by_distributor"][distributor] += amount
                            dashboard_data["customer_revenue"][customer] = dashboard_data["customer_revenue"].get(customer, 0) + amount
                            
                            # 2. Monthly Trendline
                            dashboard_data["monthly_trend"][month_key] = dashboard_data["monthly_trend"].get(month_key, 0) + amount
                            
                            # 3. Top Books
                            dashboard_data["top_books"][title] = dashboard_data["top_books"].get(title, 0) + net_copies
                            
                            # 4. Subject Distribution (Simple string matching)
                            t_lower = title.lower()
                            if "math" in t_lower: dashboard_data["subject_distribution"]["Maths"] += net_copies
                            elif "phy" in t_lower: dashboard_data["subject_distribution"]["Physics"] += net_copies
                            elif "che" in t_lower: dashboard_data["subject_distribution"]["Chemistry"] += net_copies
                            elif "bot" in t_lower: dashboard_data["subject_distribution"]["Botany"] += net_copies
                            elif "zoo" in t_lower: dashboard_data["subject_distribution"]["Zoology"] += net_copies
                            elif "skt" in t_lower or "sanskrit" in t_lower: dashboard_data["subject_distribution"]["Sanskrit"] += net_copies
                            else: dashboard_data["subject_distribution"]["Other"] += net_copies

                except Exception as e:
                    print(f"Error parsing date: {e}")
                    continue

    # Sort Top Books and keep only Top 10 to prevent chart clutter
    sorted_books = dict(sorted(dashboard_data["top_books"].items(), key=lambda item: item[1], reverse=True)[:10])
    dashboard_data["top_books"] = sorted_books
    
    # Sort monthly trend chronologically
    dashboard_data["monthly_trend"] = dict(sorted(dashboard_data["monthly_trend"].items()))

    return jsonify(dashboard_data)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)