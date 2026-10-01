import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime

# ==========================================
# 1. إعداد قاعدة البيانات
# ==========================================
conn = sqlite3.connect('master_gold_erp.db', check_same_thread=False)
c = conn.cursor()

c.executescript('''
    CREATE TABLE IF NOT EXISTS Models (
        ModelCode TEXT PRIMARY KEY, Category TEXT, Department TEXT, Unit TEXT, Weight REAL
    );
    CREATE TABLE IF NOT EXISTS Orders (
        OrderID INTEGER PRIMARY KEY AUTOINCREMENT, Branch TEXT, OrderDate TEXT
    );
    CREATE TABLE IF NOT EXISTS OrderDetails (
        ID INTEGER PRIMARY KEY AUTOINCREMENT, OrderID INTEGER, ModelCode TEXT, 
        Size TEXT, RequestedQty INTEGER, ActualQty INTEGER, Notes TEXT
    );
    CREATE TABLE IF NOT EXISTS Vault (
        ModelCode TEXT, Size TEXT, Quantity INTEGER, PRIMARY KEY(ModelCode, Size)
    );
''')
conn.commit()

# ==========================================
# 2. إعداد واجهة الويب
# ==========================================
st.set_page_config(page_title="ماستر جولد - التخطيط والإنتاج", layout="wide")
st.sidebar.title("ماستر جولد للذهب")
st.sidebar.subheader("قسم التخطيط والتنظيم")

menu = ["تسجيل أوردر جديد", "جرد الخزنة", "تجميع وإصدار أوامر التشغيل", "كتالوج الموديلات"]
choice = st.sidebar.radio("القائمة الرئيسية", menu)

# ==========================================
# 3. شاشة تسجيل أوردر جديد
# ==========================================
if choice == "تسجيل أوردر جديد":
    st.header("📝 تسجيل أوردر فرع جديد")
    
    col1, col2 = st.columns(2)
    branch_name = col1.text_input("اسم الفرع (مثال: فرع التجمع الخامس)")
    order_date = col2.date_input("تاريخ الأوردر", datetime.today())
    
    st.markdown("---")
    st.subheader("إضافة موديل للأوردر")
    model_code = st.text_input("كود الموديل").strip().upper()
    
    if model_code:
        c.execute("SELECT Category, Department, Unit, Weight FROM Models WHERE ModelCode=?", (model_code,))
        model_data = c.fetchone()
        
        if not model_data:
            st.warning("⚠️ هذا الموديل غير مسجل في الكتالوج. يرجى إدخال بياناته لحفظها تلقائياً.")
            with st.form("new_model_form"):
                cat = st.selectbox("الصنف", ["غويشة", "خاتم", "دبلة", "كوليه", "حلق", "أسورة", "سلسلة", "انسيال", "طقم"])
                dept = st.selectbox("قسم التشغيل", ["شمع", "هولو", "سي إن سي", "صب"])
                unit = st.selectbox("طريقة البيع (للحسابات)", ["جوز", "فردة", "طقم"])
                weight = st.number_input("الوزن التقريبي (جرام)", min_value=0.0, step=0.1)
                
                if st.form_submit_button("حفظ الموديل في الكتالوج"):
                    c.execute("INSERT INTO Models VALUES (?,?,?,?,?)", (model_code, cat, dept, unit, weight))
                    conn.commit()
                    st.success("✅ تم حفظ الموديل بنجاح! يمكنك الآن استكمال الأوردر.")
                    st.rerun()
        else:
            category, department, unit, weight = model_data
            st.info(f"📌 تفاصيل الموديل: الصنف ({category}) - القسم ({department}) - طريقة البيع ({unit})")
            
            with st.form("add_to_order_form"):
                if category == "غويشة":
                    size = st.selectbox("المقاس", ["19", "20", "21", "22", "23", "24"])
                elif category in ["كوليه", "حلق", "سلسلة", "طقم"]:
                    size = st.selectbox("المقاس", ["بدون مقاس"])
                else:
                    size = st.text_input("المقاس")
                
                req_qty = st.number_input(f"العدد المطلوب ({unit})", min_value=1, step=1)
                notes = st.text_input("ملاحظات التصنيع")
                
                if st.form_submit_button("إضافة للأوردر"):
                    if branch_name:
                        c.execute("SELECT OrderID FROM Orders WHERE Branch=? AND OrderDate=?", (branch_name, str(order_date)))
                        order_id = c.fetchone()
                        if not order_id:
                            c.execute("INSERT INTO Orders (Branch, OrderDate) VALUES (?,?)", (branch_name, str(order_date)))
                            order_id = c.lastrowid
                        else:
                            order_id = order_id[0]
                        
                        actual_qty = req_qty * 2 if unit == "جوز" else req_qty
                        
                        c.execute("INSERT INTO OrderDetails (OrderID, ModelCode, Size, RequestedQty, ActualQty, Notes) VALUES (?,?,?,?,?,?)",
                                  (order_id, model_code, str(size), req_qty, actual_qty, notes))
                        conn.commit()
                        st.success(f"✅ تم إضافة الصنف للأوردر! (العدد الفعلي للتشغيل: {actual_qty} قطعة)")
                    else:
                        st.error("برجاء إدخال اسم الفرع أولاً!")

# ==========================================
# 4. شاشة جرد الخزنة
# ==========================================
elif choice == "جرد الخزنة":
    st.header("📦 إدارة جرد الخزنة")
    
    with st.form("vault_form"):
        col1, col2, col3 = st.columns(3)
        v_model = col1.text_input("كود الموديل").strip().upper()
        v_size = col2.text_input("المقاس (اكتب 'بدون مقاس' إذا لزم)")
        v_qty = col3.number_input("العدد المتوفر (بالقطعة/الفردة)", min_value=0, step=1)
        
        if st.form_submit_button("تحديث الخزنة"):
            if v_model:
                c.execute("INSERT OR REPLACE INTO Vault (ModelCode, Size, Quantity) VALUES (?,?,?)", (v_model, v_size, v_qty))
                conn.commit()
                st.success("✅ تم تحديث الخزنة بنجاح.")
                
    st.markdown("---")
    st.subheader("الرصيد الحالي في الخزنة")
    vault_df = pd.read_sql_query("SELECT ModelCode as 'الكود', Size as 'المقاس', Quantity as 'العدد الفعلي' FROM Vault WHERE Quantity > 0", conn)
    st.dataframe(vault_df, use_container_width=True)

# ==========================================
# 5. التخطيط واستخراج أوامر التشغيل
# ==========================================
elif choice == "تجميع وإصدار أوامر التشغيل":
    st.header("⚙️ التخطيط وورقة التشغيل المجمعة")
    
    if st.button("🚀 تنفيذ وخصم الخزنة وإصدار أوامر الشغل", type="primary"):
        orders_df = pd.read_sql_query("""
            SELECT 
                o.ModelCode, m.Department, o.Size, o.Notes, SUM(o.ActualQty) as TotalRequired 
            FROM OrderDetails o
            JOIN Models m ON o.ModelCode = m.ModelCode
            GROUP BY o.ModelCode, m.Department, o.Size, o.Notes
        """, conn)
        
        if orders_df.empty:
            st.warning("لا توجد أوردرات معلقة لتشغيلها.")
        else:
            vault_df = pd.read_sql_query("SELECT ModelCode, Size, Quantity as VaultQty FROM Vault", conn)
            merged_df = pd.merge(orders_df, vault_df, on=['ModelCode', 'Size'], how='left')
            merged_df['VaultQty'] = merged_df['VaultQty'].fillna(0)
            
            production_list = []
            
            for index, row in merged_df.iterrows():
                model, dept, size, notes, req, in_vault = row['ModelCode'], row['Department'], row['Size'], row['Notes'], row['TotalRequired'], row['VaultQty']
                
                if in_vault >= req:
                    to_produce = 0
                    new_vault = in_vault - req
                else:
                    to_produce = req - in_vault
                    new_vault = 0
                
                if to_produce > 0:
                    production_list.append({
                        'القسم': dept, 'كود الموديل': model, 'المقاس': size,
                        'المطلوب تشغيله (قطعة)': to_produce, 'ملاحظات': notes
                    })
                
                c.execute("UPDATE Vault SET Quantity=? WHERE ModelCode=? AND Size=?", (new_vault, model, size))
            
            conn.commit()
            c.execute("DELETE FROM OrderDetails")
            c.execute("DELETE FROM Orders")
            conn.commit()
            
            production_df = pd.DataFrame(production_list)
            
            if not production_df.empty:
                st.success("✅ تم تجميع الأوامر وخصم الخزنة بنجاح! حمل ملف التشغيل الآن:")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for dept in production_df['القسم'].unique():
                        dept_df = production_df[production_df['القسم'] == dept].drop(columns=['القسم'])
                        dept_df = dept_df.sort_values(by=['المقاس'])
                        dept_df.to_excel(writer, sheet_name=f'قسم_{dept}', index=False)
                
                st.download_button(
                    label="📥 تحميل ملف Excel مقسم بالأقسام",
                    data=output.getvalue(),
                    file_name=f"أوامر_التشغيل_{datetime.today().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("👍 الخزنة غطت جميع طلبات الفروع ولا يوجد نواقص للتشغيل.")

# ==========================================
# 6. كتالوج الموديلات
# ==========================================
elif choice == "كتالوج الموديلات":
    st.header("📚 الكتالوج وقاعدة بيانات الموديلات")
    models_df = pd.read_sql_query("SELECT ModelCode as 'الكود', Category as 'الصنف', Department as 'القسم', Unit as 'وحدة البيع', Weight as 'الوزن' FROM Models", conn)
    st.dataframe(models_df, use_container_width=True)
