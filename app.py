import joblib
import pandas as pd
from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask_cors import CORS
import ollama
from datetime import datetime
import pytz  
from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import os
import re
from collections import Counter

app = Flask(__name__)

# ✅ Enable CORS for all routes
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*")

# ✅ Database Connection (MySQL)
DB_URL = "mysql+mysqlconnector://root:root@localhost:3306/fraud_detection_system"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

# ✅ Ensure fraud_cases table exists
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fraud_cases (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id VARCHAR(50) NOT NULL,
            country VARCHAR(100) NOT NULL,
            account_type VARCHAR(50) NOT NULL,
            deposit_amount INT NOT NULL,
            withdrawal_amount INT NOT NULL,
            num_trades INT NOT NULL,
            avg_trade_amount INT NOT NULL,
            trade_duration INT NOT NULL,
            total_profit INT NOT NULL,
            fees_paid FLOAT NOT NULL,
            payment_method VARCHAR(50) NOT NULL,
            risk_level VARCHAR(50) NOT NULL,
            detection_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
        )
    """))
    conn.commit()

# ✅ Load Trained Fraud Detection Model
model = joblib.load("fraud_model.pkl")
    
@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.json  # Get JSON input

        # ✅ Convert categorical features to category dtype
        categorical_features = ["country", "account_type", "payment_method"]
        for col in categorical_features:
            if col in data:
                data[col] = str(data[col])  # Ensure it's a string before conversion

        df = pd.DataFrame([data])  # Convert to DataFrame

        # ✅ Remove client_id before making a prediction
        if "client_id" in df:
            df = df.drop(columns=["client_id"])
            
        # ✅ Ensure categorical columns are recognized as category dtype
        for col in categorical_features:
            df[col] = df[col].astype("category")

        # ✅ Run prediction using the LightGBM model
        risk_level = model.predict(df)[0]  # Model directly predicts the risk level

        # ✅ Ensure Malaysia Time (UTC+8) for detection timestamp
        malaysia_tz = pytz.timezone("Asia/Kuala_Lumpur")
        detection_time = datetime.now(malaysia_tz).strftime("%Y-%m-%d %H:%M:%S")

        # ✅ Insert transaction into database
        with engine.connect() as conn:
            conn.execute(text(""" 
                INSERT INTO fraud_cases (client_id, detection_timestamp, country, account_type, deposit_amount, withdrawal_amount, num_trades, avg_trade_amount, trade_duration, total_profit, fees_paid, payment_method, risk_level)
                VALUES (:client_id, :detection_timestamp, :country, :account_type, :deposit_amount, :withdrawal_amount, :num_trades, :avg_trade_amount, :trade_duration, :total_profit, :fees_paid, :payment_method, :risk_level)
            """), {
                "client_id": data["client_id"],
                "detection_timestamp": detection_time,
                "country": data["country"],
                "account_type": data["account_type"],
                "deposit_amount": data["deposit_amount"],
                "withdrawal_amount": data["withdrawal_amount"],
                "num_trades": data["num_trades"],
                "avg_trade_amount": data["avg_trade_amount"],
                "trade_duration": data["trade_duration"],
                "total_profit": data["total_profit"],
                "fees_paid": data["fees_paid"],
                "payment_method": data["payment_method"],
                "risk_level": risk_level
            })
            conn.commit()

        # ✅ Send fraud alert **only if risk is high**
        if risk_level == "High":
            socketio.emit("fraud_alert", {"message": "Fraud detected!", "data": data})

        return jsonify({"risk_level": risk_level})

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/fraud_cases', methods=['GET'])
def get_fraud_cases():
    with engine.connect() as conn:
        conn.execute(text("SET time_zone = '+08:00';"))  # Ensure retrieval in Malaysia Time
        result = conn.execute(text("SELECT * FROM fraud_cases"))
        fraud_list = [dict(row._mapping) for row in result]
    return jsonify(fraud_list)


@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    try:
        data = request.json
        client_id = data.get("client_id")

        if not client_id:
            return jsonify({"error": "Client ID is required"}), 400

        with engine.connect() as conn:
            conn.execute(text("SET time_zone = '+08:00';"))  # Ensure retrieval in Malaysia Time
            result = conn.execute(text("""
                SELECT * FROM fraud_cases WHERE client_id = :client_id ORDER BY id DESC LIMIT 1
            """), {"client_id": client_id})
            transaction = result.fetchone()

        if not transaction:
            return jsonify({"error": "No transaction found for this client"}), 404

        transaction_data = dict(transaction._mapping)

        # ✅ Construct fraud summary prompt
        summary_prompt = f"""
        You are a trading fraud analyst. Your task is to summarize the rationale behind the assigned fraud risk level based on the provided transaction details.

        ### **Instructions:**
        - **Do not alter the assigned Risk Level.** Use the exact value in **Risk Level**.
        - **Do not introduce new risk assessments.** 
        - The summary must be **clear, professional, and limited to 30 words**.
        - **Avoid "I" statements.** Ensure neutrality and factual accuracy.

        ### **Transaction Details:**
        - **Country:** {transaction_data['country']}
        - **Account Type:** {transaction_data['account_type']}
        - **Deposit Amount:** {transaction_data['deposit_amount']}
        - **Withdrawal Amount:** {transaction_data['withdrawal_amount']}
        - **Number of Trades:** {transaction_data['num_trades']}
        - **Average Trade Amount:** {transaction_data['avg_trade_amount']}
        - **Trade Duration:** {transaction_data['trade_duration']}
        - **Total Profit:** {transaction_data['total_profit']}
        - **Fees Paid:** {transaction_data['fees_paid']}
        - **Payment Method:** {transaction_data['payment_method']}
        - **Risk Level:** {transaction_data['risk_level']} 

        ### **Fraud Risk Summary Guidelines:**
        - **High Risk:** **Large deposits with minimal trading, rapid withdrawals, or unusual patterns suggest potential illicit activity, requiring immediate account restrictions.**
        - **Medium Risk:** **Irregular trading patterns, inconsistent withdrawals, or high-risk payment methods indicate moderate risk, necessitating further review.**
        - **Low Risk:** **Minor anomalies in deposit or withdrawal behavior suggest low fraud likelihood, though periodic monitoring is advised.**
        - **No Risk:** **Transaction patterns are consistent with normal trading behavior, showing no anomalies or risks, requiring no further action.**
        """


        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": summary_prompt}]
        )

        fraud_reason = response['message']['content']

        return jsonify({
            "client_id": transaction_data['client_id'],
            "risk_level": transaction_data['risk_level'],  
            "reason": fraud_reason
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/generate_report', methods=['POST'])
def generate_report():
    try:
        print("✅ Received request for /generate_report")  # Debugging log

        data = request.json
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if not start_date or not end_date:
            print("❌ Missing start_date or end_date")  # Debugging log
            return jsonify({"error": "Start date and end date are required"}), 400

        # ✅ Ensure end_date includes full day by setting time to 23:59:59
        end_date = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


        with engine.connect() as conn:
            conn.execute(text("SET time_zone = '+08:00';"))
            result = conn.execute(text("""
                SELECT * FROM fraud_cases
                WHERE detection_timestamp >= :start_date AND detection_timestamp < :end_date
                ORDER BY detection_timestamp DESC
            """), {"start_date": start_date, "end_date": end_date})

            transactions = result.fetchall()

        print(f"📝 Transactions found: {len(transactions)}")  # Debugging log

        if not transactions:
            return jsonify({"error": "No transactions found within the selected date range"}), 404

        fraud_cases = [dict(row._mapping) for row in transactions]
        total_cases = len(fraud_cases)  

        # ✅ Extract Key Statistics
        high_risk_cases = [c for c in fraud_cases if c["risk_level"] == "High Risk"]
        medium_risk_cases = [c for c in fraud_cases if c["risk_level"] == "Medium Risk"]
        low_risk_cases = [c for c in fraud_cases if c["risk_level"] == "Low Risk"]
        no_risk_cases = [c for c in fraud_cases if c["risk_level"] == "No Risk"]
        
        risk_counts = {"High Risk": 0, "Medium Risk": 0, "Low Risk": 0, "No Risk": 0}
        total_deposits = 0
        total_withdrawals = 0
        total_fees_paid = 0
        payment_counts = Counter()

        for case in fraud_cases:
            risk_counts[case["risk_level"]] += 1
            total_deposits += case["deposit_amount"]
            total_withdrawals += case["withdrawal_amount"]
            total_fees_paid += case["fees_paid"]
            payment_counts[case["payment_method"]] += 1

        high_risk_count = risk_counts["High Risk"]
        medium_risk_count = risk_counts["Medium Risk"]
        low_risk_count = risk_counts["Low Risk"]
        no_risk_count = risk_counts["No Risk"]

        high_risk_percentage = round((high_risk_count / total_cases) * 100, 2) if total_cases else 0
        medium_risk_percentage = round((medium_risk_count / total_cases) * 100, 2) if total_cases else 0
        low_risk_percentage = round((low_risk_count / total_cases) * 100, 2) if total_cases else 0
        no_risk_percentage = round((no_risk_count / total_cases) * 100, 2) if total_cases else 0

        total_payments = sum(payment_counts.values())

        payment_usage = {
            method: round((count / total_payments) * 100, 2) if total_payments else 0
            for method, count in payment_counts.items()
        }


        # ✅ Extract all unique countries from fraud cases
        countries = set(c["country"] for c in fraud_cases)

        # ✅ Dynamically generate the country-wise fraud case breakdown
        country_data = [
            {
                "country": country,
                "total_cases": sum(1 for c in fraud_cases if c["country"] == country),
                "high_risk": sum(1 for c in fraud_cases if c["country"] == country and c["risk_level"] == "High Risk"),
                "medium_risk": sum(1 for c in fraud_cases if c["country"] == country and c["risk_level"] == "Medium Risk"),
                "low_risk": sum(1 for c in fraud_cases if c["country"] == country and c["risk_level"] == "Low Risk"),
                "no_risk": sum(1 for c in fraud_cases if c["country"] == country and c["risk_level"] == "No Risk"),
            }
            for country in countries
        ]


        # ✅ Convert timestamps to Malaysia Time (UTC+8)
        malaysia_tz = pytz.timezone("Asia/Kuala_Lumpur")
        fraud_cases_sorted = sorted(fraud_cases, key=lambda x: x["detection_timestamp"])
        earliest_detection_date = fraud_cases_sorted[0]["detection_timestamp"]
        latest_detection_date = fraud_cases_sorted[-1]["detection_timestamp"]
        earliest_detection_date = earliest_detection_date.astimezone(malaysia_tz).strftime("%Y-%m-%d %H:%M:%S")
        latest_detection_date = latest_detection_date.astimezone(malaysia_tz).strftime("%Y-%m-%d %H:%M:%S")


        # ✅ Generate the Fraud Report Prompt
        fraud_report_prompt = f"""
        You are a **fraud detection analyst**. Your task is to generate a **detailed fraud report** strictly based on the provided database records. The report should focus on **presenting recorded data accurately** without assumptions.

        ---

        ## **📝 Trading Fraud Report: {start_date} - {end_date}**  
        This section provides an overview of the transactions analyzed during the specified period.

        - **Total Transactions:** {total_cases}  
        - **Earliest Recorded Detection:** {earliest_detection_date}  
        - **Latest Recorded Detection:** {latest_detection_date}  

        Describe the volume of transactions observed and any notable patterns in the detection timestamps.

        ---

        ## **1️⃣ Risk Level Breakdown**  
        Provide a **detailed** breakdown of fraud risk levels.

        | **Risk Level** | **Number of Cases** |  
        |--------------|----------------|  
        | **High Risk** | {high_risk_count} |  
        | **Medium Risk** | {medium_risk_count} |  
        | **Low Risk** | {low_risk_count} |  
        | **No Risk** | {no_risk_count} |  

        Discuss:
        - Trends in fraud risk levels.
        - If certain risk levels were more prevalent than others.
        - If any specific patterns emerged for high or medium-risk cases.

        ---

        ## **2️⃣ Financial Transactions Breakdown**  
        Provide a **detailed** financial impact report for the transactions recorded.

        | **Category** | **Total Amount (USD)** |  
        |--------------|----------------|  
        | **Total Deposits** | ${total_deposits:,.2f} |  
        | **Total Withdrawals** | ${total_withdrawals:,.2f} |  
        | **Total Fees Paid** | ${total_fees_paid:,.2f} |  

        For each risk level, analyze the total financial amounts:

        | **Risk Level** | **Total Deposits (USD)** | **Total Withdrawals (USD)** |  
        |--------------|----------------|----------------|  
        | **High Risk** | ${sum(c['deposit_amount'] for c in high_risk_cases):,.2f} | ${sum(c['withdrawal_amount'] for c in high_risk_cases):,.2f} |  
        | **Medium Risk** | ${sum(c['deposit_amount'] for c in medium_risk_cases):,.2f} | ${sum(c['withdrawal_amount'] for c in medium_risk_cases):,.2f} |  
        | **Low Risk** | ${sum(c['deposit_amount'] for c in low_risk_cases):,.2f} | ${sum(c['withdrawal_amount'] for c in low_risk_cases):,.2f} |  
        | **No Risk** | ${sum(c['deposit_amount'] for c in no_risk_cases):,.2f} | ${sum(c['withdrawal_amount'] for c in no_risk_cases):,.2f} |  

        Discuss:
        - The financial trends across risk levels.
        - Any discrepancies between deposits and withdrawals.
        - Whether high-risk transactions had **unusual** financial patterns.

        ---

        ## **3️⃣ Payment Method Usage Analysis**  
        Detail how different payment methods were utilized.

        | **Payment Method** | **Usage Percentage (%)** |  
        |--------------|----------------|  
        {payment_usage}  

        Discuss:
        - Which payment methods were most commonly used.
        - If high-risk transactions were associated with specific payment methods.
        - Any anomalies in the payment method distribution.

        ---

        ## **4️⃣ Country-Wise Fraud Distribution**  
        Analyze fraud cases across different countries.

        | **Country** | **Total Cases** | **High-Risk** | **Medium-Risk** | **Low-Risk** | **No-Risk** |  
        |--------------|----------------|----------------|----------------|----------------|----------------|  
        {country_data}  

        Discuss:
        - Which countries had the highest fraud cases.
        - If any regions exhibited higher fraud risk.
        - Any patterns in fraud cases related to geography.

        ---

        ## **5️⃣ Detailed Fraudulent Transaction Patterns**  
        Examine transaction behaviors observed in fraudulent cases.

        **High-Risk Transactions**  
        - Were large deposits followed by immediate withdrawals?  
        - Did multiple accounts share the same payment method?  
        - Were trading volumes abnormally low compared to deposits?  

        **Medium-Risk Transactions**  
        - Were irregular withdrawal patterns observed?  
        - Did suspicious login attempts occur from different locations?  
        - Did transactions involve high-risk payment methods?  

        **Low-Risk Transactions**  
        - Did any inconsistencies appear in deposit-to-withdrawal ratios?  
        - Were small anomalies detected in trading behaviors?  

        **No-Risk Transactions**  
        - Were deposits and withdrawals stable?  
        - Did these transactions align with normal trading activity?  

        Ensure all details are **strictly derived from recorded transactions**.

        ---

        ## **6️⃣ Key Findings and Transactional Insights**  
        Provide a **comprehensive** breakdown of key fraud trends.
        Example:
        - **High-Risk Transactions:** {high_risk_percentage}% of transactions were high risk.  
        - **Common Fraud Patterns:** Discuss trends from observed transactions.  
        - **Frequently Used Payment Methods in Fraudulent Cases:** Identify which payment methods were commonly involved in fraud.  
        - **Fraud Distribution by Country:** Highlight key countries with elevated fraud cases.  

        Write this in **formal business language**, ensuring accuracy without speculation.

        """

        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": fraud_report_prompt}]
        )

        #print("🔍 Ollama response:", response)
        
        fraud_report = response['message']['content']

        # ✅ Ensure the save directory exists
        report_dir = r"C:\Users\user\Downloads\DerivAI Hackathon\fraud_detection_system"
        if not os.path.exists(report_dir):
            os.makedirs(report_dir)  # Create directory if it doesn't exist

        # ✅ Generate PDF Report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"fraud_report_{timestamp}.pdf"
        report_path = os.path.join(report_dir, report_filename)

        pdf = canvas.Canvas(report_path, pagesize=letter)
        pdf.setFont("Helvetica", 12)

        # ✅ PDF Formatting
        doc = SimpleDocTemplate(report_path, pagesize=letter,
                                rightMargin=50, leftMargin=50,
                                topMargin=50, bottomMargin=50)

        styles = getSampleStyleSheet()
        styles["BodyText"].alignment = TA_JUSTIFY
        styles["BodyText"].fontSize = 12
        styles["BodyText"].leading = 16

        bold_style = ParagraphStyle(
            "BoldStyle",
            parent=styles["BodyText"],
            fontSize=12,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=10,
            fontName="Helvetica-Bold"
        )

        def format_bold(text):
            """Replaces Markdown-style **bold** text with correct <b> tags."""
            return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

        content = []
        for line in fraud_report.split("\n"):
            if line.strip():
                formatted_text = format_bold(line)  # ✅ Fix the incorrect tag formatting
                content.append(Paragraph(formatted_text, styles["BodyText"]))
                content.append(Spacer(1, 0.2 * inch))  # ✅ Add spacing between paragraphs

        doc.build(content)

        # ✅ Check if file is created and has content
        if os.path.exists(report_path):
            file_size = os.path.getsize(report_path)
            print(f"✅ Report generated at: {report_path} (Size: {file_size} bytes)")

            if file_size < 1000:
                print("🚨 Warning: PDF file size is too small. The file may be corrupted.")

        return send_file(report_path, as_attachment=False, download_name=report_filename)

    except Exception as e:
        print("🚨 Exception:", str(e))  # Debugging
        return jsonify({"error": str(e)})
 
if __name__ == '__main__':
    socketio.run(app, debug=True)