import streamlit as st
import base64
import json
import sqlite3
import pandas as pd
from datetime import datetime
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models

# ==========================================
import os
SECRET_ID = os.environ.get("SECRET_ID", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
# ==========================================

st.set_page_config(page_title="票账猫", page_icon="🐱", layout="wide")
st.title("🐱 票账猫")
st.caption("喵一下，账好了。")

# --- 初始化数据库 ---
def init_db():
    conn = sqlite3.connect('piaozhangmao.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS invoices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  invoice_number TEXT,
                  invoice_date TEXT,
                  amount REAL,
                  seller TEXT,
                  upload_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 侧边栏：历史账单 ---
st.sidebar.header("📊 历史记账看板")
conn = sqlite3.connect('piaozhangmao.db')
df_history = pd.read_sql("SELECT * FROM invoices ORDER BY upload_time DESC", conn)
if not df_history.empty:
    st.sidebar.metric("累计记账金额", f"¥{df_history['amount'].sum():.2f}")
    st.sidebar.metric("累计发票张数", len(df_history))
    st.sidebar.dataframe(df_history[['invoice_number', 'amount', 'seller']], use_container_width=True)
else:
    st.sidebar.info("暂无历史记账记录")
conn.close()

# --- 主界面 ---
uploaded = st.file_uploader("上传发票图片", type=["jpg", "jpeg", "png"])

if uploaded:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.image(uploaded, caption="已上传发票", use_container_width=True)
    
    with col2:
        if st.button("开始识别", type="primary", use_container_width=True):
            with st.spinner("喵喵正在识别中..."):
                try:
                    # 1. 读取图片并转为 Base64
                    image_bytes = uploaded.getvalue()
                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                    # 2. 初始化腾讯云客户端
                    cred = credential.Credential(SECRET_ID, SECRET_KEY)
                    client = ocr_client.OcrClient(cred, "ap-guangzhou")
                    req = models.VatInvoiceOCRRequest()
                    req.ImageBase64 = image_base64
                    
                    # 3. 发起请求
                    resp = client.VatInvoiceOCR(req)
                    resp_dict = json.loads(resp.to_json_string())

                    st.success("识别成功！")
                    
                    # 4. 更智能的字段提取
                    if "VatInvoiceInfos" in resp_dict:
                        info_list = resp_dict["VatInvoiceInfos"]
                        extracted = {}
                        for item in info_list:
                            name = item.get("Name", "")
                            value = item.get("Value", "")
                            
                            # 只要名字里包含这些关键字，就抓取进来
                            if "发票号码" in name: extracted["发票号码"] = value
                            if "开票日期" in name: extracted["开票日期"] = value
                            if "价税合计" in name or "金额" in name: 
                                if "金额" not in extracted: # 优先抓价税合计
                                    extracted["金额"] = value.replace("¥", "").replace("￥", "").replace(",", "")
                            if "销售方" in name or "名称" in name: 
                                if "销售方名称" not in extracted:
                                    extracted["销售方名称"] = value
                        
                        # 保存到数据库
                        if "金额" in extracted and extracted["金额"]:
                            try:
                                amt = float(extracted["金额"])
                                conn = sqlite3.connect('piaozhangmao.db')
                                c = conn.cursor()
                                c.execute("INSERT INTO invoices (invoice_number, invoice_date, amount, seller, upload_time) VALUES (?, ?, ?, ?, ?)",
                                          (extracted.get("发票号码", ""), extracted.get("开票日期", ""), amt, extracted.get("销售方名称", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                conn.commit()
                                conn.close()
                            except ValueError:
                                pass

                        st.json(extracted)
                        
                        if "金额" in extracted:
                            st.metric("发票金额", f"¥{extracted['金额']}")
                    else:
                        st.warning("未检测到标准发票字段，展示原始数据：")
                        st.json(resp_dict)

                except Exception as e:
                    st.error(f"识别失败：{str(e)}")
                    st.info("请检查：1. 密钥是否正确且未被禁用；2. 账号余额或免费额度是否充足。")

# --- 刷新按钮 ---
if st.sidebar.button("🔄 刷新看板"):
    st.rerun()