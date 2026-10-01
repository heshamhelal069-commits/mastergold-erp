import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime

# ==========================================
# 1. إعداد قاعدة البيانات (نسخة جديدة V2)
# ==========================================
conn = sqlite3.connect('master_gold_erp_v2.db', check_same_thread=False)
c = conn.cursor()

c.executescript('''
    CREATE TABLE IF NOT EXISTS Models (
        ModelCode TEXT PRIMARY KEY, Category TEXT, Department TEXT, Unit TEXT, Weight REAL
    );
    CREATE TABLE IF NOT EXISTS Orders (
        OrderID INTEGER PRIMARY KEY AUTOINCREMENT, BatchCode TEXT, Branch TEXT, OrderDate TEXT
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

menu = ["تسجيل أوردر جديد", "جرد الخزنة", "تجميع وإصدار أوامر التشغيل", "كتالوج الموديلات", "تعديل/إلغاء أوردر"]
choice = st.sidebar.radio("القائمة الرئيسية", menu)

# ==========================================
# 3. شاشة تسجيل أوردر جديد (التصميم الجديد)
# ==========================================
if choice == "تسجيل أوردر جديد":
    st.header("📝 تسجيل أوردر فرع جديد")
    
    # القسم الأول: ثوابت الفرع (ثابتة ومكشوفة)
    col1, col2, col3 = st.columns(3)
    batch_code = col1.text_input("كود التجميعة/الأسبوع (مثال: أسبوع 1 - شهر 10)", "أسبوع 1")
    branch_name = col2.text_input("اسم الفرع (مثال: فرع التجمع الخامس)")
    order_date = col3.date_input("تاريخ الأوردر", datetime.today())
    
    st.markdown("---")
    
    # القسم الثاني: جدول الإدخال السريع
    st.subheader("إضافة أصناف للأوردر")
    
    if 'temp_order' not in st.session_state:
        st.session_state.temp_order = []
        
    with st.form("quick_add_form", clear_on_submit=True):
        st.write("أدخل الكود واضغط Enter، أو املأ باقي الخانات واضغط 'إضافة للجدول المؤقت'")
        col_code, col_size, col_qty, col_notes = st.columns([2, 1, 1, 2])
        new_code = col_code.text_input("كود الموديل").strip().upper()
        new_size = col_size.selectbox("المقاس (لغير الغوايش اختر 'بدون مقاس')", ["بدون مقاس", "19", "20", "21", "22", "23", "24", "أخرى"])
        if new_size == "أخرى":
            new_size = col_size.text_input("حدد المقاس")
        new_qty = col_qty.number_input("العدد المطلوب", min_value=1, step=1)
        new_notes = col_notes.text_input("ملاحظات")
        
        submitted = st.form_submit_button("إضافة للجدول المؤقت")
        
        if submitted and new_code:
            c.execute("SELECT Category, Department, Unit, Weight FROM Models WHERE ModelCode=?", (new_code,))
            model_data = c.fetchone()
            
            if not model_data:
                st.warning(f"⚠️ الموديل '{new_code}' غير مسجل. يرجى إضافته للكتالوج أولاً (استخدم قائمة 'كتالوج الموديلات').")
            else:
                category, department, unit, weight = model_data
                actual_qty = new_qty * 2 if unit == "جوز" else new_qty
                
                st.session_state.temp_order.append({
                    "كود الموديل": new_code,
                    "الصنف": category,
                    "المقاس": str(new_size),
                    "العدد المطلوب": new_qty,
                    "العدد الفعلي": actual_qty,
                    "ملاحظات": new_notes
                })
                st.success(f"تم الإضافة للجدول المؤقت: {new_code}")

    # القسم الرابع: جدول العرض الفوري المجمع (الماتريكس)
    if st.session_state.temp_order:
        st.markdown("---")
        st.subheader(f"🛒 الجدول المؤقت (الفرع: {branch_name} | التجميعة: {batch_code})")
        temp_df = pd.DataFrame(st.session_state.temp_order)
        
        is_bangle = temp_df['الصنف'] == 'غويشة'
        
        if is_bangle.any():
            st.write("**جدول الغوايش (ماتريكس)**")
            bangle_df = temp_df[is_bangle]
            pivot_df = bangle_df.pivot_table(index='كود الموديل', columns='المقاس', values='العدد المطلوب', aggfunc='sum', fill_value=0)
            
            all_sizes = ["19", "20", "21", "22", "23", "24"]
            for s in all_sizes:
                if s not in pivot_df.columns:
                    pivot_df[s] = 0
            pivot_df = pivot_df[all_sizes]
            
            pivot_df.columns = [f"مقاس {s}" for s in pivot_df.columns]
            pivot_df['إجمالي الصنف'] = pivot_df.sum(axis=1)
            
            st.dataframe(pivot_df.style.format(precision=0), use_container_width=True)
            
        if (~is_bangle).any():
            st.write("**جدول باقي الأصناف**")
            st.dataframe(temp_df[~is_bangle][["كود الموديل", "الصنف", "المقاس", "العدد المطلوب", "ملاحظات"]], use_container_width=True)
            
        if st.button("💾 حفظ الأوردر النهائي (وخصم الخزنة)"):
            if not branch_name or not batch_code:
                st.error("برجاء إدخال اسم الفرع وكود التجميعة قبل الحفظ!")
            else:
                c.execute("INSERT INTO Orders (BatchCode, Branch, OrderDate) VALUES (?,?,?)", (batch_code, branch_name, str(order_date)))
                order_id = c.lastrowid
                
                for item in st.session_state.temp_order:
                    c.execute("INSERT INTO OrderDetails (OrderID, ModelCode, Size, RequestedQty, ActualQty, Notes) VALUES (?,?,?,?,?,?)",
                              (order_id, item["كود الموديل"], item["المقاس"], item["العدد المطلوب"], item["العدد الفعلي"], item["ملاحظات"]))
                    
                    c.execute("SELECT Quantity FROM Vault WHERE ModelCode=? AND Size=?", (item["كود الموديل"], item["المقاس"]))
                    vault_record = c.fetchone()
                    
                    if vault_record:
                        current_qty = vault_record[0]
                        new_qty = max(0, current_qty - item["العدد الفعلي"])
                        c.execute("UPDATE Vault SET Quantity=? WHERE ModelCode=? AND Size=?", (new_qty, item["كود الموديل"], item["المقاس"]))
                    
                conn.commit()
                st.session_state.temp_order = [] 
                st.success(f"✅ تم حفظ أوردر {branch_name} تحت تجميعة ({batch_code}) وخصم الكميات المتوفرة من الخزنة!")
                st.rerun()
                
        if st.button("🗑️ مسح الجدول المؤقت"):
            st.session_state.temp_order = []
            st.rerun()

# ==========================================
# 4. شاشة جرد الخزنة
# ==========================================
elif choice == "جرد الخزنة":
    st.header("📦 إدارة جرد الخزنة")
    
    with st.form("vault_form"):
        col1, col2, col3 = st.columns(3)
        v_model = col1.text_input("كود الموديل").strip().upper()
        v_size = col2.text_input("المقاس (اكتب 'بدون مقاس' لغير الغوايش)")
        v_qty = col3.number_input("العدد (إضافة أو تعديل)", min_value=0, step=1)
        
        if st.form_submit_button("تحديث الخزنة"):
            if v_model:
                c.execute("INSERT OR REPLACE INTO Vault (ModelCode, Size, Quantity) VALUES (?,?,?)", (v_model, v_size, v_qty))
                conn.commit()
                st.success("✅ تم تحديث الخزنة بنجاح.")
                
    st.markdown("---")
    st.subheader("الرصيد الحالي")
    vault_df = pd.read_sql_query("SELECT ModelCode as 'الكود', Size as 'المقاس', Quantity as 'العدد المتوفر' FROM Vault WHERE Quantity > 0", conn)
    st.dataframe(vault_df, use_container_width=True)

# ==========================================
# 5. التخطيط واستخراج أوامر التشغيل
# ==========================================
elif choice == "تجميع وإصدار أوامر التشغيل":
    st.header("⚙️ أوامر التشغيل المجمعة (للنواقص فقط)")
    
    batches_df = pd.read_sql_query("SELECT DISTINCT BatchCode FROM Orders", conn)
    
    if batches_df.empty:
        st.info("لا توجد تجميعات مسجلة حتى الآن.")
    else:
        batches_list = batches_df['BatchCode'].tolist()
        selected_batch = st.selectbox("📌 اختر كود التجميعة (الأسبوع) لاستخراج نواقصه:", batches_list)
        
        orders_df = pd.read_sql_query("""
            SELECT 
                o.ModelCode, m.Department, o.Size, o.Notes, SUM(o.ActualQty) as TotalRequired 
            FROM OrderDetails o
            JOIN Models m ON o.ModelCode = m.ModelCode
            JOIN Orders ord ON o.OrderID = ord.OrderID
            WHERE ord.BatchCode = ?
            GROUP BY o.ModelCode, m.Department, o.Size, o.Notes
        """, conn, params=(selected_batch,))
        
        if orders_df.empty:
            st.info("👍 لا توجد نواقص للتشغيل في هذه التجميعة.")
        else:
            st.dataframe(orders_df.rename(columns={'ModelCode':'الكود', 'Department':'القسم', 'Size':'المقاس', 'Notes':'ملاحظات', 'TotalRequired':'العدد المطلوب (نواقص)'}), use_container_width=True)
            
            if st.button(f"📥 تحميل أوامر تشغيل مصنع ({selected_batch})", type="primary"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for dept in orders_df['Department'].unique():
                        dept_df = orders_df[orders_df['Department'] == dept].drop(columns=['Department'])
                        dept_df = dept_df.sort_values(by=['Size'])
                        dept_df.rename(columns={'ModelCode':'الكود', 'Size':'المقاس', 'Notes':'ملاحظات', 'TotalRequired':'العدد المطلوب'}).to_excel(writer, sheet_name=f'قسم_{dept}', index=False)
                
                st.download_button(
                    label="تحميل الملف (Excel)",
                    data=output.getvalue(),
                    file_name=f"نواقص_المصنع_{selected_batch}_{datetime.today().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            st.markdown("---")
            if st.button("⚠️ أرشفة التجميعة (بعد التسليم للمصنع نهائياً)"):
                c.execute("DELETE FROM OrderDetails WHERE OrderID IN (SELECT OrderID FROM Orders WHERE BatchCode=?)", (selected_batch,))
                c.execute("DELETE FROM Orders WHERE BatchCode=?", (selected_batch,))
                conn.commit()
                st.success(f"تم أرشفة ومسح أوامر تجميعة '{selected_batch}' بنجاح.")
                st.rerun()

# ==========================================
# 6. كتالوج الموديلات
# ==========================================
elif choice == "كتالوج الموديلات":
    st.header("📚 الكتالوج وقاعدة بيانات الموديلات")
    
    with st.expander("➕ إضافة موديل جديد للكتالوج"):
        with st.form("new_model_catalog_form"):
            c_code = st.text_input("كود الموديل").strip().upper()
            c_cat = st.selectbox("الصنف", ["غويشة", "خاتم", "دبلة", "كوليه", "حلق", "أسورة", "سلسلة", "انسيال", "طقم"])
            c_dept = st.selectbox("قسم التشغيل", ["شمع", "هولو", "سي إن سي", "صب"])
            c_unit = st.selectbox("طريقة البيع (للحسابات)", ["جوز", "فردة", "طقم"])
            c_weight = st.number_input("الوزن التقريبي (جرام)", min_value=0.0, step=0.1)
            
            if st.form_submit_button("حفظ"):
                if c_code:
                    c.execute("INSERT OR REPLACE INTO Models VALUES (?,?,?,?,?)", (c_code, c_cat, c_dept, c_unit, c_weight))
                    conn.commit()
                    st.success("تم الحفظ!")
                    
    models_df = pd.read_sql_query("SELECT ModelCode as 'الكود', Category as 'الصنف', Department as 'القسم', Unit as 'وحدة البيع', Weight as 'الوزن' FROM Models", conn)
    st.dataframe(models_df, use_container_width=True)

# ==========================================
# 7. تعديل/إلغاء أوردر
# ==========================================
elif choice == "تعديل/إلغاء أوردر":
    st.header("🔧 تعديل أو إلغاء أوردر")
    st.write("هنا يمكنك مراجعة الأوردرات المسجلة. (الميزة قيد التطوير الكامل - سيتم إضافتها في التحديث القادم حسب الحاجة).")
    
    all_orders = pd.read_sql_query("""
        SELECT o.BatchCode as 'التجميعة', o.OrderID as 'رقم الأوردر', o.Branch as 'الفرع', o.OrderDate as 'التاريخ', 
               od.ModelCode as 'الكود', od.Size as 'المقاس', od.RequestedQty as 'الكمية المطلوبة'
        FROM Orders o
        JOIN OrderDetails od ON o.OrderID = od.OrderID
        ORDER BY o.BatchCode DESC, o.OrderID DESC
    """, conn)
    st.dataframe(all_orders, use_container_width=True)
