import streamlit as st
import json
import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from st_click_detector import click_detector

st.set_page_config(page_title="Solaso 售票系統", page_icon="🎫", layout="centered")

# ════════════════════════════════════════════════
#  設定區 — 修改這裡調整座位配置與票價
# ════════════════════════════════════════════════

EVENT = {
    "name": "Solaso 成果發表",
    "date": "2026 年 X 月 X 日",
    "venue": "場地待定",
    "bank_info": "臺灣銀行 (004) 帳號：1234-5678-9012",
}

SECTIONS = {
    "左區": {"code": "L", "seats": 5},
    "中區": {"code": "C", "seats": 10},
    "右區": {"code": "R", "seats": 5},
}

TIERS = {
    "VVIP":  {"rows": (1, 5),   "price": 1200, "color": "#FFD700"},
    "VIP":   {"rows": (6, 10),  "price": 800,  "color": "#9B59B6"},
    "一般票": {"rows": (11, 20), "price": 500,  "color": "#3498DB"},
    "自由座": {"rows": (21, 30), "price": 0,    "color": "#2ECC71"},
}

TOTAL_ROWS = 30
MAX_PER_ORDER = 10


# ════════════════════════════════════════════════
#  座位工具
# ════════════════════════════════════════════════

def tier_for_row(row):
    for name, t in TIERS.items():
        if t["rows"][0] <= row <= t["rows"][1]:
            return name
    return ""


def make_sid(row, sec_code, num):
    return f"{row}-{sec_code}-{num}"


def parse_sid(sid):
    r, s, n = sid.split("-")
    return int(r), s, int(n)


def seat_label(sid):
    row, sec, num = parse_sid(sid)
    sec_names = {"L": "左", "C": "中", "R": "右"}
    return f"第{row}排 {sec_names[sec]}區 第{num}座"


def taken_seats(orders):
    out = set()
    for o in orders:
        if o["status"] != "已取消" and o.get("seats"):
            raw = o["seats"]
            sl = json.loads(raw) if isinstance(raw, str) else (raw or [])
            out.update(sl)
    return out


def free_count(orders):
    return sum(
        o["quantity"] for o in orders
        if o["status"] != "已取消" and o.get("ticket_type") == "自由座"
    )


def free_capacity():
    r = TIERS["自由座"]["rows"]
    return (r[1] - r[0] + 1) * sum(s["seats"] for s in SECTIONS.values())


def parse_seats_field(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


# ════════════════════════════════════════════════
#  座位圖 HTML
# ════════════════════════════════════════════════

def render_seat_map(taken, selected=None, active_tier=None):
    """
    active_tier=None → 全部顯示（唯讀，給後台用）
    active_tier="VVIP" → 該票種可點擊，其餘淡化
    """
    sel = selected or set()

    html = """<style>
.smap{text-align:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif;user-select:none}
.stage{background:#333;color:#fff;padding:8px;margin-bottom:10px;border-radius:5px;font-size:14px}
.srow{display:flex;align-items:center;justify-content:center;margin:1px 0}
.rlbl{width:28px;text-align:right;margin-right:3px;font-size:10px;color:#888}
.s{width:22px;height:22px;margin:1px;border-radius:3px;display:inline-block;box-sizing:border-box}
a.s{text-decoration:none;cursor:pointer;transition:transform 0.1s}
a.s:hover{transform:scale(1.2);opacity:0.85}
.gap{width:10px;display:inline-block}
.dim{opacity:0.2}
.tl{font-size:10px;color:#aaa;margin:5px 0 1px}
.lgd{margin-top:10px;font-size:11px}
.li{display:inline-block;padding:2px 8px;border-radius:3px;margin:2px}
.sec-hdr{display:flex;justify-content:center;font-size:11px;color:#666;margin-bottom:3px}
</style>
<div class="smap">
<div class="stage">🎭 舞台</div>
<div class="sec-hdr">
<span style="width:28px"></span>
<span style="width:120px;text-align:center">左區</span>
<span style="width:10px"></span>
<span style="width:240px;text-align:center">中區</span>
<span style="width:10px"></span>
<span style="width:120px;text-align:center">右區</span>
</div>
"""

    cur_tier = ""
    for row in range(1, TOTAL_ROWS + 1):
        tier = tier_for_row(row)
        ti = TIERS[tier]
        is_active = (active_tier is None or tier == active_tier)

        if tier != cur_tier:
            price_txt = f"NT${ti['price']:,}" if ti["price"] else "免費"
            html += f'<div class="tl">── {tier} ({price_txt}) ──</div>'
            cur_tier = tier

        html += f'<div class="srow"><span class="rlbl">{row}</span>'

        for sinfo in SECTIONS.values():
            code = sinfo["code"]
            for n in range(1, sinfo["seats"] + 1):
                sid = make_sid(row, code, n)
                title = seat_label(sid)

                if sid in taken:
                    dim = "" if is_active else " dim"
                    html += f'<span class="s{dim}" style="background:#d5d5d5;" title="已售"></span>'
                elif sid in sel:
                    html += f'<a href="#" id="{sid}" class="s" style="background:#E74C3C;" title="{title} ✓"></a>'
                elif is_active and active_tier is not None:
                    html += f'<a href="#" id="{sid}" class="s" style="background:{ti["color"]};" title="{title}"></a>'
                elif active_tier is None:
                    html += f'<span class="s" style="background:{ti["color"]};" title="{title}"></span>'
                else:
                    html += f'<span class="s dim" style="background:{ti["color"]};"></span>'

            if code != "R":
                html += '<div class="gap"></div>'

        html += "</div>"

    html += '<div class="lgd">'
    html += '<span class="li" style="background:#FFD700">VVIP</span>'
    html += '<span class="li" style="background:#9B59B6;color:#fff">VIP</span>'
    html += '<span class="li" style="background:#3498DB;color:#fff">一般</span>'
    html += '<span class="li" style="background:#2ECC71;color:#fff">自由座</span>'
    html += '<span class="li" style="background:#d5d5d5">已售</span>'
    if active_tier is not None:
        html += '<span class="li" style="background:#E74C3C;color:#fff">已選</span>'
    html += "</div></div>"
    return html


# ════════════════════════════════════════════════
#  儲存層
# ════════════════════════════════════════════════

def _use_supabase():
    try:
        return bool(st.secrets.get("supabase", {}).get("url"))
    except Exception:
        return False


if _use_supabase():
    from supabase import create_client

    @st.cache_resource
    def _db():
        return create_client(
            st.secrets["supabase"]["url"],
            st.secrets["supabase"]["key"],
        )

    def load_orders():
        return _db().table("orders").select("*").order("created_at", desc=True).execute().data

    def insert_order(data):
        _db().table("orders").insert(data).execute()

    def update_status(order_id, new_status):
        _db().table("orders").update({"status": new_status}).eq("order_id", order_id).execute()

else:
    _LOCAL = os.path.join(os.path.dirname(__file__), "orders.json")

    def _read():
        if not os.path.exists(_LOCAL):
            return []
        with open(_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(data):
        with open(_LOCAL, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_orders():
        return _read()

    def insert_order(data):
        orders = _read()
        data["created_at"] = datetime.now().isoformat()
        orders.insert(0, data)
        _write(orders)

    def update_status(order_id, new_status):
        orders = _read()
        for o in orders:
            if o["order_id"] == order_id:
                o["status"] = new_status
                break
        _write(orders)


# ════════════════════════════════════════════════
#  通用工具
# ════════════════════════════════════════════════

def gen_order_id():
    return "SLS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def admin_pw():
    try:
        return st.secrets["admin"]["password"]
    except Exception:
        return "admin"


import re
def is_valid_email(email):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))


def is_valid_phone(phone):
    digits = phone.replace("-", "").replace(" ", "")
    return bool(re.match(r'^09\d{8}$', digits))


def send_email(to_email, subject, html_body):
    """透過 Gmail SMTP 寄信，失敗時靜默（不影響訂單流程）"""
    try:
        sender = st.secrets["email"]["sender"]
        password = st.secrets["email"]["password"]
    except Exception:
        return  # 未設定 email secrets，跳過

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{EVENT['name']} <{sender}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
    except Exception:
        pass  # 寄信失敗不影響訂單


def send_order_received(order):
    """寄送訂單已收到通知"""
    seats = parse_seats_field(order.get("seats"))
    seats_text = "、".join(seat_label(s) for s in seats) if seats else "自由座（無指定座位）"

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#333;">🎫 {EVENT['name']} — 訂單已收到</h2>
      <p>您好 {order['name']}，</p>
      <p>我們已收到您的訂單，以下是訂單資訊：</p>
      <table style="border-collapse:collapse;width:100%;margin:16px 0;">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>訂單編號</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['order_id']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>姓名</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['name']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>電話</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['phone']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>Email</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['email']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>票種</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['ticket_type']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>座位</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{seats_text}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>張數</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['quantity']} 張</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>金額</b></td>
            <td style="padding:8px;border:1px solid #ddd;">NT${order['total_amount']:,}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>狀態</b></td>
            <td style="padding:8px;border:1px solid #ddd;color:#e67e22;"><b>⏳ 待核帳</b></td></tr>
      </table>
      <div style="background:#fff3cd;padding:12px;border-radius:6px;margin:16px 0;">
        <b>⚠️ 請注意：</b>訂單尚未完成！<br>
        請匯款至 <b>{EVENT['bank_info']}</b>，<br>
        主辦方核對帳款後，您會收到確認信。
      </div>
      <p style="color:#888;font-size:12px;">此為系統自動發送，請勿直接回覆。</p>
    </div>
    """
    send_email(order["email"], f"【{EVENT['name']}】訂單已收到 — {order['order_id']}", html)


def send_order_confirmed(order):
    """寄送付款已確認通知"""
    seats = parse_seats_field(order.get("seats"))
    seats_text = "、".join(seat_label(s) for s in seats) if seats else "自由座（無指定座位）"

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#333;">✅ {EVENT['name']} — 付款已確認</h2>
      <p>您好 {order['name']}，</p>
      <p>您的訂單已確認付款完成！</p>
      <table style="border-collapse:collapse;width:100%;margin:16px 0;">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>訂單編號</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['order_id']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>姓名</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['name']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>電話</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order.get('phone', '—')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>Email</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order.get('email', '—')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>票種</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['ticket_type']}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>座位</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{seats_text}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>張數</b></td>
            <td style="padding:8px;border:1px solid #ddd;">{order['quantity']} 張</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9;"><b>狀態</b></td>
            <td style="padding:8px;border:1px solid #ddd;color:#27ae60;"><b>✅ 已確認</b></td></tr>
      </table>
      <div style="background:#d4edda;padding:12px;border-radius:6px;margin:16px 0;">
        🎉 感謝您的購票！期待在演出當天見到您。
      </div>
      <p style="color:#888;font-size:12px;">此為系統自動發送，請勿直接回覆。</p>
    </div>
    """
    send_email(order["email"], f"【{EVENT['name']}】付款已確認 — {order['order_id']}", html)


# ════════════════════════════════════════════════
#  頁面：購票
# ════════════════════════════════════════════════

def page_buy():
    col_logo, col_title = st.columns([1, 3])
    with col_logo:
        st.image("logo.jpg", width=120)
    with col_title:
        st.title(f"{EVENT['name']}售票")
        st.caption(f"📅 {EVENT['date']}　｜　📍 {EVENT['venue']}")
    st.divider()

    if "order_ok" in st.session_state:
        oid = st.session_state.pop("order_ok")
        is_free = st.session_state.pop("order_free", False)
        st.success(f"訂單送出成功！訂單編號：**{oid}**，請妥善保存。")
        st.balloons()
        if not is_free:
            st.info("主辦方將於 1–2 個工作天內核對帳款。")
        st.divider()

    orders = load_orders()
    taken = taken_seats(orders)

    tier = st.selectbox(
        "選擇票種",
        list(TIERS.keys()),
        format_func=lambda t: (
            f"{t} — NT${TIERS[t]['price']:,}" if TIERS[t]["price"] else f"{t} — 免費"
        ),
    )
    ti = TIERS[tier]

    # ── 自由座 ──
    if tier == "自由座":
        used = free_count(orders)
        cap = free_capacity()
        remain = cap - used
        st.caption(f"自由座剩餘 {remain} / {cap} 個名額")

        st.markdown(render_seat_map(taken, active_tier="自由座"), unsafe_allow_html=True)

        if remain <= 0:
            st.error("自由座已額滿！")
            return

        with st.form("free_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("姓名 *")
            phone = c2.text_input("聯絡電話 *")
            email = st.text_input("Email *")
            qty = st.number_input("人數", 1, min(MAX_PER_ORDER, remain), 1)
            ok = st.form_submit_button("免費預約", use_container_width=True)

        if ok:
            if not name.strip() or not phone.strip() or not email.strip():
                st.error("請填寫所有必填欄位（姓名、電話、Email）")
                return
            if not is_valid_phone(phone.strip()):
                st.error("電話格式不正確，請輸入 09 開頭的 10 碼手機號碼")
                return
            if not is_valid_email(email.strip()):
                st.error("Email 格式不正確，請輸入有效的 Email 地址")
                return
            if free_count(load_orders()) + qty > cap:
                st.error("名額不足，請減少人數")
                return

            oid = gen_order_id()
            insert_order({
                "order_id": oid,
                "name": name.strip(),
                "phone": phone.strip(),
                "email": email.strip() or None,
                "ticket_type": "自由座",
                "quantity": qty,
                "total_amount": 0,
                "bank_last_five": "00000",
                "status": "已確認",
                "seats": None,
            })
            send_order_confirmed({"order_id": oid, "name": name.strip(),
                "email": email.strip(), "ticket_type": "自由座",
                "quantity": qty, "total_amount": 0, "seats": None})
            st.session_state["order_ok"] = oid
            st.session_state["order_free"] = True
            st.rerun()
        return

    # ── 付費座位：點擊選位 ──

    # 切換票種時清空選擇
    if st.session_state.get("_tier") != tier:
        st.session_state._tier = tier
        st.session_state.selected_seats = set()

    sel = st.session_state.get("selected_seats", set())
    qty = len(sel)
    price = ti["price"]
    total = price * qty

    # 選位摘要（座位圖上方，隨時可見）
    if qty > 0:
        st.success(
            f"✅ 已選 {qty} 個座位 — NT${total:,}　｜　"
            + "、".join(seat_label(s) for s in sorted(sel))
        )
        col_clear, col_hint = st.columns([1, 2])
        if col_clear.button("🗑️ 清除選擇"):
            st.session_state.selected_seats = set()
            st.rerun()
        col_hint.caption("⬇️ 往下捲動填寫資料完成購票")
    else:
        st.info(f"點擊座位圖選擇 {tier} 座位（最多 {MAX_PER_ORDER} 個），再點一次可取消")

    # 座位圖
    map_html = render_seat_map(taken, sel, active_tier=tier)
    clicked = click_detector(map_html, key="seatmap")

    # 防止無限 rerun：只在偵測到「新的」點擊時才處理
    last_click = st.session_state.get("_last_click", "")
    if clicked and clicked != last_click:
        st.session_state._last_click = clicked
        if clicked in sel:
            sel.discard(clicked)
        elif len(sel) < MAX_PER_ORDER:
            sel.add(clicked)
        else:
            st.warning(f"每筆訂單最多選 {MAX_PER_ORDER} 個座位")
        st.session_state.selected_seats = sel
        st.rerun()

    if qty == 0:
        return

    # 結帳區
    st.divider()
    st.markdown(f"### 🧾 已選 {qty} 個座位　｜　應付金額：NT${total:,}")
    st.info(f"請匯款至：**{EVENT['bank_info']}**")

    with st.form("paid_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("姓名 *")
        phone = c2.text_input("聯絡電話 *")
        email = st.text_input("Email *")
        bank_code = st.text_input("匯款帳號後五碼 *（匯款後再填寫）", max_chars=5)
        ok = st.form_submit_button("送出訂單", use_container_width=True)

    if ok:
        if not name.strip() or not phone.strip() or not email.strip() or not bank_code.strip():
            st.error("請填寫所有必填欄位（姓名、電話、Email、後五碼）")
            return
        if not is_valid_phone(phone.strip()):
            st.error("電話格式不正確，請輸入 09 開頭的 10 碼手機號碼")
            return
        if not is_valid_email(email.strip()):
            st.error("Email 格式不正確，請輸入有效的 Email 地址")
            return
        if len(bank_code) != 5 or not bank_code.isdigit():
            st.error("後五碼請填寫 5 位數字")
            return

        fresh = load_orders()
        conflict = sel & taken_seats(fresh)
        if conflict:
            st.error(f"座位已被他人購買：{', '.join(seat_label(s) for s in conflict)}，請重新選擇")
            return

        oid = gen_order_id()
        existing = {o["order_id"] for o in fresh}
        while oid in existing:
            oid = gen_order_id()

        order_data = {
            "order_id": oid,
            "name": name.strip(),
            "phone": phone.strip(),
            "email": email.strip(),
            "ticket_type": tier,
            "quantity": qty,
            "total_amount": total,
            "bank_last_five": bank_code,
            "status": "待核帳",
            "seats": json.dumps(sorted(sel)),
        }
        insert_order(order_data)
        send_order_received(order_data)
        st.session_state.selected_seats = set()
        st.session_state["order_ok"] = oid
        st.rerun()


# ════════════════════════════════════════════════
#  頁面：查詢訂單
# ════════════════════════════════════════════════

def page_query():
    st.title("🔍 訂單查詢")
    st.caption("輸入訂單編號查詢目前狀態")

    oid = st.text_input("訂單編號（例如 SLS-A3B7K2）").strip().upper()
    if not oid:
        return

    orders = load_orders()
    match = [o for o in orders if o["order_id"] == oid]
    if not match:
        st.warning("查無此訂單，請確認編號")
        return

    o = match[0]
    icon = {"待核帳": "🟡", "已確認": "🟢", "已取消": "🔴"}.get(o["status"], "⚪")

    st.markdown(f"### {icon} 狀態：{o['status']}")
    c1, c2 = st.columns(2)
    c1.markdown(f"**姓名：** {o['name']}")
    c2.markdown(f"**票種：** {o['ticket_type']}")
    c1.markdown(f"**張數：** {o['quantity']}")
    c2.markdown(f"**金額：** NT${o['total_amount']:,}")

    seats = parse_seats_field(o.get("seats"))
    if seats:
        st.markdown("**座位：** " + "、".join(seat_label(s) for s in seats))

    st.caption(f"下單時間：{o.get('created_at', '—')}")


# ════════════════════════════════════════════════
#  頁面：管理後台
# ════════════════════════════════════════════════

def page_admin():
    st.title("📊 訂單管理後台")

    pw = st.text_input("管理員密碼", type="password")
    if not pw:
        return
    if pw != admin_pw():
        st.error("密碼錯誤")
        return

    orders = load_orders()
    confirmed = [o for o in orders if o["status"] == "已確認"]
    pending = [o for o in orders if o["status"] == "待核帳"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("已確認票數", f"{sum(o['quantity'] for o in confirmed)} 張")
    c2.metric("已入帳金額", f"${sum(o['total_amount'] for o in confirmed):,}")
    c3.metric("待核帳", f"{len(pending)} 筆")
    c4.metric("總訂單", f"{len(orders)} 筆")

    with st.expander("📍 座位圖"):
        st.markdown(render_seat_map(taken_seats(orders)), unsafe_allow_html=True)

    st.divider()

    st.subheader(f"待核帳（{len(pending)} 筆）")
    if pending:
        for o in pending:
            seats = parse_seats_field(o.get("seats"))
            seats_txt = "、".join(seat_label(s) for s in seats) if seats else ""

            with st.expander(
                f"📌 {o['order_id']}　{o['name']}　{o['ticket_type']}　"
                f"${o['total_amount']:,}　後五碼 {o['bank_last_five']}"
            ):
                st.markdown(
                    f"**張數：** {o['quantity']}　｜　**電話：** {o['phone']}　｜　"
                    f"**Email：** {o.get('email') or '—'}"
                )
                if seats_txt:
                    st.markdown(f"**座位：** {seats_txt}")
                st.caption(f"下單：{o.get('created_at', '—')}")

                a1, a2, _ = st.columns([1, 1, 3])
                if a1.button("✅ 確認收款", key=f"ok_{o['order_id']}"):
                    update_status(o["order_id"], "已確認")
                    if o.get("email"):
                        send_order_confirmed(o)
                    st.rerun()
                if a2.button("❌ 取消", key=f"no_{o['order_id']}"):
                    update_status(o["order_id"], "已取消")
                    st.rerun()
    else:
        st.info("沒有待核帳訂單")

    st.divider()

    st.subheader("所有訂單")
    filt = st.selectbox("篩選", ["全部", "待核帳", "已確認", "已取消"])
    show = orders if filt == "全部" else [o for o in orders if o["status"] == filt]

    if show:
        import pandas as pd

        df = pd.DataFrame(show)
        cols = [c for c in [
            "order_id", "name", "phone", "ticket_type", "quantity",
            "total_amount", "bank_last_five", "seats", "status", "created_at",
        ] if c in df.columns]
        labels = {
            "order_id": "訂單編號", "name": "姓名", "phone": "電話",
            "ticket_type": "票種", "quantity": "張數", "total_amount": "金額",
            "bank_last_five": "後五碼", "seats": "座位", "status": "狀態",
            "created_at": "下單時間",
        }
        st.dataframe(df[cols].rename(columns=labels), use_container_width=True, hide_index=True)

        csv = df[cols].rename(columns=labels).to_csv(index=False)
        st.download_button("📥 匯出 CSV", csv, "solaso_orders.csv", "text/csv")
    else:
        st.info("沒有符合條件的訂單")


# ════════════════════════════════════════════════
#  主程式
# ════════════════════════════════════════════════

page = st.sidebar.radio(
    "導覽",
    ["🎫 購票", "🔍 查詢訂單", "🔒 管理後台"],
    label_visibility="collapsed",
)

if not _use_supabase():
    st.sidebar.caption("⚠️ 本地模式（orders.json）")

if page == "🎫 購票":
    page_buy()
elif page == "🔍 查詢訂單":
    page_query()
else:
    page_admin()
