import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)
CORS(app) 

# Connect to MongoDB Atlas using the URI from the .env file
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
        return jsonify({"error": "Start date and end date are required."}), 400

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    revenues = {}
    books_sold_by_distributor = {}

    # Iterate through all collections
    for collection_name in db.list_collection_names():
        # Using the Collection Name as the Distributor Name
        distributor = collection_name
        collection = db[collection_name]
        
        # Initialize dictionaries for this collection/distributor
        if distributor not in revenues:
            revenues[distributor] = 0
        if distributor not in books_sold_by_distributor:
            books_sold_by_distributor[distributor] = {}
        
        for doc in collection.find():
            for txn in doc.get("Transactions", []):
                txn_date_raw = txn.get("Date")
                
                if not txn_date_raw:
                    continue
                
                try:
                    # 1. If PyMongo already converted the BSON date to a Python datetime
                    if isinstance(txn_date_raw, datetime):
                        txn_date = txn_date_raw.replace(tzinfo=None) 
                    
                    # 2. If it is a raw dictionary (e.g., {"$date": "..."})
                    elif isinstance(txn_date_raw, dict) and "$date" in txn_date_raw:
                        date_val = txn_date_raw["$date"]
                        if isinstance(date_val, (int, float)): 
                            txn_date = datetime.fromtimestamp(date_val / 1000.0)
                        else:
                            date_str = str(date_val)[:10]
                            txn_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    # 3. If it is a plain string
                    elif isinstance(txn_date_raw, str):
                        date_str = txn_date_raw[:10]
                        txn_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    else:
                        continue 
                        
                    # Check if the transaction falls within the requested date range
                    if start_date <= txn_date <= end_date:
                        for item in txn.get("Items", []):
                            title = item.get("Title")
                            net_copies = item.get("Net_Copies", 0)
                            amount = item.get("Amount", 0)

                            revenues[distributor] += amount
                            books_sold_by_distributor[distributor][title] = books_sold_by_distributor[distributor].get(title, 0) + net_copies

                except Exception as e:
                    print(f"Error parsing date {txn_date_raw} for document {doc.get('_id')}: {e}")
                    continue

    return jsonify({
        "revenues": revenues,
        "books_sold": books_sold_by_distributor
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
