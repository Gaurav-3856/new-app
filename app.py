import streamlit as st
import pandas as pd
from fuzzywuzzy import fuzz
import io
import re

st.set_page_config(page_title="GST Reconciliation Tool", layout="wide")
st.title("📊 GST Reconciliation: GSTR-2B vs Purchase Register")

# Upload files
col1, col2 = st.columns(2)
with col1:
    purchase_file = st.file_uploader("Upload Purchase Register", type=["xlsx"], key="purchase")
with col2:
    gstr2b_file = st.file_uploader("Upload GSTR-2B", type=["xlsx"], key="gstr2b")

if purchase_file and gstr2b_file:
    try:
        purchase_df = pd.read_excel(purchase_file)
        gstr2b_df = pd.read_excel(gstr2b_file)
    except Exception as e:
        st.error(f"❌ Error reading files: {e}")
        st.stop()

    st.success("✅ Files uploaded successfully!")

    st.subheader("🔧 Select Matching Columns")

    with st.form("column_selection"):
        pr_cols = purchase_df.columns.tolist()
        g2b_cols = gstr2b_df.columns.tolist()

        st.markdown("### 🧾 Purchase Register Columns")
        pr_inv_col = st.selectbox("Invoice Number", pr_cols)
        pr_party_col = st.selectbox("Party Name", pr_cols)
        pr_amt_col = st.selectbox("Taxable Amount", pr_cols)
        pr_gst_col = st.selectbox("GSTIN (Optional)", ["None"] + pr_cols)

        st.markdown("### 📥 GSTR-2B Columns")
        g2b_inv_col = st.selectbox("Invoice Number (GSTR-2B)", g2b_cols)
        g2b_party_col = st.selectbox("Party Name (GSTR-2B)", g2b_cols)
        g2b_amt_col = st.selectbox("Taxable Amount (GSTR-2B)", g2b_cols)
        g2b_gst_col = st.selectbox("GSTIN (Optional - GSTR-2B)", ["None"] + g2b_cols)

        strictness = st.slider("🧠 Matching Strictness (% Fuzzy Score)", min_value=50, max_value=100, value=80, step=5)
        submit_btn = st.form_submit_button("🔄 Run Reconciliation")

    if submit_btn:
        st.info("🔍 Matching invoices...")

        def clean_inv(inv, n=5):
            return re.sub(r"\D", "", str(inv))[-n:]

        def clean_text(x):
            return str(x).strip().lower()

        purchase_df["_inv"] = purchase_df[pr_inv_col].apply(clean_inv)
        gstr2b_df["_inv"] = gstr2b_df[g2b_inv_col].apply(clean_inv)
        purchase_df["_party"] = purchase_df[pr_party_col].apply(clean_text)
        gstr2b_df["_party"] = gstr2b_df[g2b_party_col].apply(clean_text)

        if pr_gst_col != "None":
            purchase_df["_gst"] = purchase_df[pr_gst_col].astype(str).str.strip().str.lower()
        else:
            purchase_df["_gst"] = ""

        if g2b_gst_col != "None":
            gstr2b_df["_gst"] = gstr2b_df[g2b_gst_col].astype(str).str.strip().str.lower()
        else:
            gstr2b_df["_gst"] = ""

        matched, unmatched_purchase, unmatched_gstr2b = [], [], gstr2b_df.copy()

        for _, pr_row in purchase_df.iterrows():
            pr_inv = pr_row["_inv"]
            pr_party = pr_row["_party"]
            pr_amt = pr_row[pr_amt_col]
            pr_gst = pr_row["_gst"]

            potential_matches = gstr2b_df[gstr2b_df["_inv"] == pr_inv]
            found = False

            for _, g2b_row in potential_matches.iterrows():
                g2b_party = g2b_row["_party"]
                g2b_amt = g2b_row[g2b_amt_col]
                g2b_gst = g2b_row["_gst"]
                party_score = fuzz.partial_ratio(pr_party, g2b_party)
                try:
                    diff = abs(float(pr_amt) - float(g2b_amt))
                except:
                    diff = 999999

                if party_score >= strictness and diff <= 1000:
                    matched.append({
                        "Invoice": pr_row[pr_inv_col],
                        "Party (Purchase)": pr_row[pr_party_col],
                        "Party (GSTR2B)": g2b_row[g2b_party_col],
                        "Amount (Purchase)": pr_amt,
                        "Amount (GSTR2B)": g2b_amt,
                        "Difference": diff,
                        "GSTIN (Purchase)": pr_gst,
                        "GSTIN (GSTR2B)": g2b_gst,
                        "Fuzzy Match %": party_score
                    })
                    unmatched_gstr2b = unmatched_gstr2b[unmatched_gstr2b[g2b_inv_col] != g2b_row[g2b_inv_col]]
                    found = True
                    break

            if not found:
                unmatched_purchase.append(pr_row)

        st.success(f"✅ Matched Invoices: {len(matched)}")
        st.warning(f"⚠️ Unmatched from Purchase Register: {len(unmatched_purchase)}")
        st.warning(f"⚠️ Unmatched from GSTR-2B: {len(unmatched_gstr2b)}")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            pd.DataFrame(matched).to_excel(writer, index=False, sheet_name="Matched")
            pd.DataFrame(unmatched_purchase).to_excel(writer, index=False, sheet_name="Unmatched_PR")
            unmatched_gstr2b.to_excel(writer, index=False, sheet_name="Unmatched_GSTR2B")
        output.seek(0)

        st.download_button("📥 Download Reconciliation Report", output, "GST_Reconciliation_Result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
