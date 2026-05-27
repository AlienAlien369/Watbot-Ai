import os
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="watbotai POC", layout="centered")

st.title("watbotai — Upload PDF & Chat (POC)")

tenant_id = st.text_input("Tenant ID", value="tenant_123")
uploaded = st.file_uploader("Upload PDF", type=["pdf"])
if st.button("Upload PDF"):
    if not uploaded:
        st.error("Choose a PDF first")
    else:
        files = {"file": (uploaded.name, uploaded.getvalue(), "application/pdf")}
        data = {"tenant_id": tenant_id}
        resp = requests.post(f"{BACKEND_URL}/upload", files=files, data=data)
        try:
            st.json(resp.json())
        except Exception:
            st.error(f"Backend error: {resp.status_code}")
            st.text(resp.text)


st.markdown("---")
st.header("Chat")
question = st.text_input("Ask something about your document", value="What is the main topic of this document?")
if st.button("Send"):
    payload = {"tenant_id": tenant_id, "question": question}
    r = requests.post(f"{BACKEND_URL}/ask", json=payload)
    st.json(r.json())

st.markdown("### Widget")
st.markdown("Use the plain HTML widget in `app/static/widget.html` (suitable for GitHub Pages).")
