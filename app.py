
import streamlit as st
import pandas as pd
from fuzzywuzzy import fuzz
import io

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

    # Column selection interface
    st.subheader("🔧 Select Matching Columns")

    with st.form("column_selection"):
        col_names = purchase_df.columns.tolist()
        gstr2b_cols = gstr2b_df.columns.tolist()

        st.markdown("### 🧾 Purchase Register Columns")
        pr_invoice_col = st.selectbox("Invoice Number", col_names)
        pr_party_col = st.selectbox("Party Name", col_names)
        pr_amount_col = st.selectbox("Taxable Amount", col_names)
        pr_gstin_col = st.selectbox("GSTIN (Optional)", ["None"] + col_names)

        st.markdown("### 📥 GSTR-2B Columns")
        g2b_invoice_col = st.selectbox("Invoice Number (GSTR-2B)", gstr2b_cols)
        g2b_party_col = st.selectbox("Party Name (GSTR-2B)", gstr2b_cols)
        g2b_amount_col = st.selectbox("Taxable Amount (GSTR-2B)", gstr2b_cols)
        g2b_gstin_col = st.selectbox("GSTIN (Optional, GSTR-2B)", ["None"] + gstr2b_cols)

        match_threshold = st.slider("🧠 Matching Strictness (Higher = Stricter)", min_value=50, max_value=100, value=80, step=1)

        submit_btn = st.form_submit_button("🔄 Run Reconciliation")

    if submit_btn:
        st.info("🔍 Matching invoices...")

        def clean_text(x):
            if pd.isna(x):
                return ""
            return str(x).strip().lower().replace(" ", "").replace("-", "").replace("/", "")

        purchase_df["_inv"] = purchase_df[pr_invoice_col].apply(clean_text)
        purchase_df["_party"] = purchase_df[pr_party_col].astype(str).str.lower()
        if pr_gstin_col != "None":
            purchase_df["_gstin"] = purchase_df[pr_gstin_col].astype(str).str.lower()

        gstr2b_df["_inv"] = gstr2b_df[g2b_invoice_col].apply(clean_text)
        gstr2b_df["_party"] = gstr2b_df[g2b_party_col].astype(str).str.lower()
        if g2b_gstin_col != "None":
            gstr2b_df["_gstin"] = gstr2b_df[g2b_gstin_col].astype(str).str.lower()

        matched = []
        unmatched_purchase = []
        unmatched_gstr2b = gstr2b_df.copy()

        for _, pr_row in purchase_df.iterrows():
            pr_inv = pr_row["_inv"]
            pr_party = pr_row["_party"]
            pr_amt = pr_row[pr_amount_col]
            pr_gstin = pr_row["_gstin"] if pr_gstin_col != "None" else None

            potential_matches = gstr2b_df[gstr2b_df["_inv"] == pr_inv]

            found = False
            for _, g2b_row in potential_matches.iterrows():
                score = fuzz.partial_ratio(pr_party, g2b_row["_party"])
                g2b_amt = g2b_row[g2b_amount_col]
                g2b_gstin = g2b_row["_gstin"] if g2b_gstin_col != "None" else None

                try:
                    diff = abs(float(pr_amt) - float(g2b_amt))
                except:
                    diff = 999999

                gstin_match = pr_gstin == g2b_gstin if pr_gstin and g2b_gstin else True

                if score >= match_threshold and diff <= 1000 and gstin_match:
                    matched.append({
                        "Invoice": pr_row[pr_invoice_col],
                        "Party (Purchase)": pr_row[pr_party_col],
                        "Party (GSTR2B)": g2b_row[g2b_party_col],
                        "Amount (Purchase)": pr_amt,
                        "Amount (GSTR2B)": g2b_amt,
                        "Difference": diff,
                        "GSTIN Match": gstin_match,
                        "Fuzzy Score": score
                    })
                    unmatched_gstr2b = unmatched_gstr2b[unmatched_gstr2b[g2b_invoice_col] != g2b_row[g2b_invoice_col]]
                    found = True
                    break

            if not found:
                unmatched_purchase.append(pr_row)

        st.success(f"✅ {len(matched)} Invoices Matched")
        st.warning(f"⚠️ {len(unmatched_purchase)} Invoices Unmatched from Purchase Register")
        st.warning(f"⚠️ {len(unmatched_gstr2b)} Invoices Unmatched from GSTR-2B")

        # Save to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            pd.DataFrame(matched).to_excel(writer, index=False, sheet_name="Matched")
            pd.DataFrame(unmatched_purchase).to_excel(writer, index=False, sheet_name="Unmatched_PR")
            unmatched_gstr2b.to_excel(writer, index=False, sheet_name="Unmatched_GSTR2B")
        output.seek(0)

        st.download_button(
            label="📥 Download Reconciliation Report",
            data=output,
            file_name="GST_Reconciliation_Result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
