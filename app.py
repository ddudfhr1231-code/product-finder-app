import streamlit as st
import pandas as pd
import calendar
from datetime import date, datetime, timezone

try:
    from supabase import create_client
except Exception:
    create_client = None


st.set_page_config(
    page_title="상품 소싱 운영툴",
    page_icon="📦",
    layout="wide"
)


# =========================
# 기본 옵션
# =========================

STATUS_OPTIONS = [
    "1차 수집",
    "영록 검토 필요",
    "추가 조사 필요",
    "샘플 구매 후보",
    "샘플 구매 완료",
    "쿠팡 등록 준비",
    "판매 테스트 중",
    "탈락"
]

CATEGORY_OPTIONS = [
    "기타",
    "생활용품",
    "차량용품",
    "세차용품",
    "주방용품",
    "수납/정리",
    "반려동물",
    "공구/DIY",
    "캠핑/아웃도어",
    "사무/문구",
    "인테리어"
]

REJECT_REASON_OPTIONS = [
    "",
    "마진 낮음",
    "경쟁 심함",
    "KC/인증 위험",
    "상표권 위험",
    "파손 위험",
    "부피 큼",
    "반품 위험",
    "상세페이지 제작 어려움",
    "쿠팡 가격 너무 낮음",
    "기타"
]

RISK_OPTIONS = [
    "파손 위험",
    "전기/배터리 제품",
    "KC 인증 필요 가능성",
    "부피 큼",
    "반품률 높을 가능성",
    "브랜드/상표권 위험",
    "쿠팡 경쟁 심함",
    "상세페이지 만들기 어려움"
]

PURCHASE_STATUS_OPTIONS = [
    "구매 예정",
    "구매 완료",
    "배송 중",
    "입고 완료",
    "품질 확인 완료",
    "판매 진행",
    "판매 보류"
]

EXPENSE_CATEGORY_OPTIONS = [
    "샘플 구매",
    "사입비",
    "국제배송비",
    "국내배송비",
    "포장재",
    "광고비",
    "쿠팡 수수료",
    "촬영/콘텐츠",
    "소프트웨어",
    "기타"
]

SALES_CHANNEL_OPTIONS = [
    "쿠팡",
    "네이버",
    "스마트스토어",
    "당근",
    "기타"
]

SOURCE_SITE_OPTIONS = [
    "1688",
    "타오바오",
    "알리바바",
    "알리익스프레스",
    "국내 도매몰",
    "오프라인 도매처",
    "기타"
]

SOURCE_CURRENCY_OPTIONS = [
    "중국 위안화(CNY)",
    "한국 원화(KRW)",
    "직접 입력"
]


# =========================
# 공통 함수
# =========================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


@st.cache_resource
def get_supabase_client():
    url = get_secret("SUPABASE_URL", "")
    key = get_secret("SUPABASE_KEY", "")

    if not url or not key or create_client is None:
        return None

    return create_client(url, key)


def get_db():
    db = get_supabase_client()
    if db is None:
        st.error("Supabase 연결이 안 되어 있습니다. Streamlit Secrets와 requirements.txt를 확인하세요.")
    return db


def load_accounts():
    accounts = []

    for i in range(1, 10):
        user_id = get_secret(f"USER{i}_ID", "")
        user_pw = get_secret(f"USER{i}_PW", "")
        user_name = get_secret(f"USER{i}_NAME", user_id)

        if user_id and user_pw:
            accounts.append({
                "id": user_id,
                "pw": user_pw,
                "name": user_name
            })

    return accounts


def current_user_name():
    return st.session_state.get("user_name", "")


def login_screen():
    st.title("상품 소싱 운영툴")
    st.caption("1688 상품 소싱, 샘플 구매, 매출, 지출, 손익을 한 곳에서 관리합니다.")

    accounts = load_accounts()

    if not accounts:
        st.error("Streamlit Secrets에 USER1_ID / USER1_PW가 없습니다.")
        st.stop()

    with st.form("login_form"):
        login_id = st.text_input("아이디")
        login_pw = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")

    if submitted:
        for account in accounts:
            if login_id == account["id"] and login_pw == account["pw"]:
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = account["id"]
                st.session_state["user_name"] = account["name"]
                st.rerun()

        st.error("아이디 또는 비밀번호가 틀렸습니다.")


def as_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def as_text(value, default=""):
    if value is None:
        return default
    return str(value)


def format_won(value):
    try:
        return f"{int(round(float(value))):,}원"
    except Exception:
        return "0원"


def split_risk_items(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def safe_select_index(options, value, default_index=0):
    if value in options:
        return options.index(value)
    return default_index


def fetch_table(table_name, order_col="created_at"):
    db = get_supabase_client()

    if db is None:
        return []
        
    try:
        response = (
            db.table(table_name)
            .select("*")
            .order(order_col, desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        st.error(f"{table_name} 불러오기 실패")
        st.code(str(e))
        return []


def get_setting_numeric(setting_id, default_value=0.0):
    db = get_supabase_client()

    if db is None:
        return default_value

    try:
        response = (
            db.table("app_settings")
            .select("value_numeric")
            .eq("id", setting_id)
            .limit(1)
            .execute()
        )

        if response.data:
            return as_float(response.data[0].get("value_numeric"), default_value)

        return default_value

    except Exception:
        return default_value


def save_setting_numeric(setting_id, value, updated_by):
    db = get_supabase_client()

    if db is None:
        return False, "Supabase 연결 실패"

    try:
        db.table("app_settings").upsert({
            "id": setting_id,
            "value_text": str(value),
            "value_numeric": float(value),
            "updated_by": updated_by,
            "updated_at": now_iso()
        }).execute()

        return True, ""

    except Exception as e:
        return False, str(e)


def get_exchange_rate_by_currency(source_currency, cny_exchange_rate):
    if source_currency == "중국 위안화(CNY)":
        return float(cny_exchange_rate)

    if source_currency == "한국 원화(KRW)":
        return 1.0

    return float(cny_exchange_rate)


def get_date_filtered_df(df, date_col, selected_date):
    if df.empty or date_col not in df.columns:
        return pd.DataFrame()

    temp = df.copy()
    temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce").dt.date

    return temp[temp[date_col] == selected_date]

def render_finance_calendar(sales_df, expense_df, purchase_df):
    st.subheader("재무 달력")
    st.caption("일요일 시작 월간 달력입니다. 날짜 칸 안에 수입, 지출, 총합이 표시되고 날짜를 누르면 아래에 상세 내역이 뜹니다.")

    today = date.today()

    if "finance_calendar_year" not in st.session_state:
        st.session_state["finance_calendar_year"] = today.year

    if "finance_calendar_month" not in st.session_state:
        st.session_state["finance_calendar_month"] = today.month

    top1, top2, top3, top4 = st.columns([1, 1, 1, 3])

    with top1:
        selected_year = st.number_input(
            "년도",
            min_value=2020,
            max_value=2100,
            value=int(st.session_state["finance_calendar_year"]),
            step=1,
            key="finance_year_input"
        )

    with top2:
        selected_month = st.selectbox(
            "월",
            list(range(1, 13)),
            index=int(st.session_state["finance_calendar_month"]) - 1,
            key="finance_month_select"
        )

    with top3:
        if st.button("이번 달 보기"):
            st.session_state["finance_calendar_year"] = today.year
            st.session_state["finance_calendar_month"] = today.month
            st.session_state["selected_finance_date"] = str(today)
            st.rerun()

    st.session_state["finance_calendar_year"] = int(selected_year)
    st.session_state["finance_calendar_month"] = int(selected_month)

    selected_year = int(st.session_state["finance_calendar_year"])
    selected_month = int(st.session_state["finance_calendar_month"])

    daily_totals = {}

    # 매출: +
    if not sales_df.empty and "sale_date" in sales_df.columns:
        temp_sales = sales_df.copy()
        temp_sales["sale_date"] = pd.to_datetime(temp_sales["sale_date"], errors="coerce").dt.date

        for _, row in temp_sales.iterrows():
            d = row.get("sale_date")

            if pd.isna(d) or d is None:
                continue

            key = str(d)

            if key not in daily_totals:
                daily_totals[key] = {
                    "income": 0,
                    "outgo": 0
                }

            daily_totals[key]["income"] += as_float(row.get("gross_sales"), 0)

    # 일반 지출: -
    if not expense_df.empty and "expense_date" in expense_df.columns:
        temp_expense = expense_df.copy()
        temp_expense["expense_date"] = pd.to_datetime(temp_expense["expense_date"], errors="coerce").dt.date

        for _, row in temp_expense.iterrows():
            d = row.get("expense_date")

            if pd.isna(d) or d is None:
                continue

            key = str(d)

            if key not in daily_totals:
                daily_totals[key] = {
                    "income": 0,
                    "outgo": 0
                }

            daily_totals[key]["outgo"] += as_float(row.get("amount"), 0)

    # 샘플/구매 지출: -
    if not purchase_df.empty and "purchase_date" in purchase_df.columns:
        temp_purchase = purchase_df.copy()
        temp_purchase["purchase_date"] = pd.to_datetime(temp_purchase["purchase_date"], errors="coerce").dt.date

        for _, row in temp_purchase.iterrows():
            d = row.get("purchase_date")

            if pd.isna(d) or d is None:
                continue

            key = str(d)

            if key not in daily_totals:
                daily_totals[key] = {
                    "income": 0,
                    "outgo": 0
                }

            daily_totals[key]["outgo"] += as_float(row.get("total_purchase_cost"), 0)

    st.divider()
    st.markdown(f"### {selected_year}년 {selected_month}월")

    # 요일 헤더: 일요일 시작
    weekday_names = ["일", "월", "화", "수", "목", "금", "토"]
    header_cols = st.columns(7)

    for i, day_name in enumerate(weekday_names):
        header_cols[i].markdown(
            f"""
            <div style="
                text-align:center;
                font-weight:700;
                padding:8px 0;
                border-bottom:1px solid #e5e7eb;
            ">
                {day_name}
            </div>
            """,
            unsafe_allow_html=True
        )

    # 일요일 시작 달력
    cal = calendar.Calendar(firstweekday=6)
    month_matrix = cal.monthdayscalendar(selected_year, selected_month)

    for week in month_matrix:
        cols = st.columns(7)

        for col_idx, day_num in enumerate(week):
            with cols[col_idx]:
                if day_num == 0:
                    st.markdown(
                        """
                        <div style="
                            height:150px;
                            border:1px solid #eeeeee;
                            border-radius:10px;
                            background-color:#fafafa;
                            margin-bottom:10px;
                        "></div>
                        """,
                        unsafe_allow_html=True
                    )
                    continue

                current_date = date(selected_year, selected_month, day_num)
                date_key = str(current_date)

                income = daily_totals.get(date_key, {}).get("income", 0)
                outgo = daily_totals.get(date_key, {}).get("outgo", 0)
                net = income - outgo

                net_sign = "+" if net >= 0 else "-"
                net_color = "#16a34a" if net >= 0 else "#dc2626"

                selected_style = ""
                if st.session_state.get("selected_finance_date") == date_key:
                    selected_style = "box-shadow:0 0 0 2px #2563eb inset;"

                st.markdown(
                    f"""
                    <div style="
                        border:1px solid #d1d5db;
                        border-radius:12px;
                        padding:10px;
                        height:150px;
                        margin-bottom:6px;
                        background-color:white;
                        {selected_style}
                    ">
                        <div style="
                            font-weight:800;
                            font-size:17px;
                            margin-bottom:12px;
                            color:#111827;
                        ">
                            {day_num}
                        </div>

                        <div style="
                            color:#2563eb;
                            font-size:14px;
                            line-height:1.5;
                        ">
                            +{int(income):,}
                        </div>

                        <div style="
                            color:#dc2626;
                            font-size:14px;
                            line-height:1.5;
                        ">
                            -{int(outgo):,}
                        </div>

                        <div style="
                            color:{net_color};
                            font-weight:800;
                            font-size:14px;
                            line-height:1.5;
                            margin-top:4px;
                        ">
                            총 {net_sign}{abs(int(net)):,}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if st.button("날짜 선택", key=f"finance_day_{date_key}"):
                    st.session_state["selected_finance_date"] = date_key
                    st.rerun()

    if "selected_finance_date" not in st.session_state:
        st.session_state["selected_finance_date"] = str(today)

    selected_date = datetime.strptime(
        st.session_state["selected_finance_date"],
        "%Y-%m-%d"
    ).date()

    st.divider()
    st.subheader(f"{selected_date} 상세 내역")

    selected_sales = get_date_filtered_df(sales_df, "sale_date", selected_date)
    selected_expenses = get_date_filtered_df(expense_df, "expense_date", selected_date)
    selected_purchases = get_date_filtered_df(purchase_df, "purchase_date", selected_date)

    income_total = (
        selected_sales["gross_sales"].sum()
        if not selected_sales.empty and "gross_sales" in selected_sales.columns
        else 0
    )

    expense_total = (
        selected_expenses["amount"].sum()
        if not selected_expenses.empty and "amount" in selected_expenses.columns
        else 0
    )

    purchase_total = (
        selected_purchases["total_purchase_cost"].sum()
        if not selected_purchases.empty and "total_purchase_cost" in selected_purchases.columns
        else 0
    )

    total_outgo = expense_total + purchase_total
    net_total = income_total - total_outgo

    detail1, detail2, detail3, detail4 = st.columns(4)

    detail1.metric("수입", format_won(income_total))
    detail2.metric("일반 지출", format_won(expense_total))
    detail3.metric("샘플/구매 지출", format_won(purchase_total))
    detail4.metric("총합", format_won(net_total))

    st.markdown("#### 매출 내역")
    show_df(selected_sales, "선택일매출")

    st.markdown("#### 일반 지출 내역")
    show_df(selected_expenses, "선택일지출")

    st.markdown("#### 샘플/구매 지출 내역")
    show_df(selected_purchases, "선택일구매")

    return selected_date


def to_df(records):
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    numeric_cols = [
        "yuan_price", "exchange_rate", "china_shipping_krw", "intl_shipping_krw",
        "domestic_shipping_krw", "extra_cost_krw", "coupang_price",
        "coupang_fee_rate", "ad_rate", "vat_rate", "risk_rate",
        "target_margin_rate", "total_unit_cost", "net_sales", "profit",
        "margin_rate", "roi_rate", "quantity", "product_amount",
        "china_shipping", "intl_shipping", "other_cost", "total_purchase_cost",
        "sale_price", "gross_sales", "product_cost", "coupang_fee",
        "shipping_cost", "ad_cost", "amount", "net_profit"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def show_df(df, label="데이터"):
    if df.empty:
        st.info(f"{label}가 없습니다.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_data = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"{label} CSV 다운로드",
        data=csv_data,
        file_name=f"{label}.csv",
        mime="text/csv",
        key=f"download_{label}"
    )


def calculate_product(
    yuan_price,
    exchange_rate,
    china_shipping_krw,
    intl_shipping_krw,
    domestic_shipping_krw,
    extra_cost_krw,
    coupang_price,
    coupang_fee_rate,
    ad_rate,
    vat_rate,
    risk_rate,
    target_margin_rate,
    competition_level,
    risk_items
):
    product_cost_krw = yuan_price * exchange_rate

    total_unit_cost = (
        product_cost_krw
        + china_shipping_krw
        + intl_shipping_krw
        + domestic_shipping_krw
        + extra_cost_krw
    )

    deduction_rate = coupang_fee_rate + ad_rate + vat_rate + risk_rate
    net_sales = coupang_price * (1 - deduction_rate / 100)
    profit = net_sales - total_unit_cost

    margin_rate = profit / coupang_price * 100 if coupang_price > 0 else 0
    roi_rate = profit / total_unit_cost * 100 if total_unit_cost > 0 else 0

    if profit <= 0:
        judgment = "탈락"
    elif margin_rate >= target_margin_rate + 5 and roi_rate >= 30 and competition_level != "높음" and len(risk_items) <= 1:
        judgment = "강력 후보"
    elif margin_rate >= target_margin_rate and roi_rate >= 20 and len(risk_items) <= 2:
        judgment = "검토 가능"
    elif margin_rate >= 5 and profit > 0:
        judgment = "보류"
    else:
        judgment = "탈락"

    return {
        "total_unit_cost": float(total_unit_cost),
        "net_sales": float(net_sales),
        "profit": float(profit),
        "margin_rate": float(margin_rate),
        "roi_rate": float(roi_rate),
        "judgment": judgment
    }

def duplicate_warnings(db, source_url, coupang_url):
    warnings = []

    def is_real_url(value):
        if not value:
            return False

        value = str(value).strip().lower()

        ignore_values = [
            "도매몰",
            "도매처",
            "국내 도매몰",
            "오프라인 도매처",
            "없음",
            "x",
            "-"
        ]

        if value in ignore_values:
            return False

        return value.startswith("http://") or value.startswith("https://")

    try:
        if is_real_url(source_url):
            res = (
                db.table("product_records")
                .select("id, product_name")
                .or_(f"source_url.eq.{source_url},product_url_1688.eq.{source_url}")
                .limit(1)
                .execute()
            )
            if res.data:
                warnings.append(f"도매 상품 URL 중복 가능: {res.data[0].get('product_name', '')}")

        if is_real_url(coupang_url):
            res = (
                db.table("product_records")
                .select("id, product_name")
                .eq("product_url_coupang", coupang_url)
                .limit(1)
                .execute()
            )
            if res.data:
                warnings.append(f"쿠팡 URL 중복 가능: {res.data[0].get('product_name', '')}")

    except Exception:
        pass

    return warnings

def product_label(row):
    return f"{row.get('id')} | {row.get('product_name', '상품명 없음')} | {row.get('status', '')} | 담당자:{row.get('manager_name', '')}"


def record_label(row, name_key="product_name"):
    name = row.get(name_key) or row.get("description") or "이름 없음"
    return f"{row.get('id')} | {name} | 담당자:{row.get('manager_name', '')}"


# =========================
# 로그인
# =========================

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()


st.sidebar.title("운영툴")
st.sidebar.write(f"로그인: **{current_user_name()}**")
st.sidebar.caption("저장/수정 시 담당자는 현재 로그인 계정으로 자동 기록됩니다.")

if st.sidebar.button("로그아웃"):
    st.session_state.clear()
    st.rerun()


# =========================
# 데이터 로드
# =========================

products = fetch_table("product_records")
purchases = fetch_table("purchase_records")
sales = fetch_table("sales_records")
expenses = fetch_table("expense_records")

product_df = to_df(products)
purchase_df = to_df(purchases)
sales_df = to_df(sales)
expense_df = to_df(expenses)

cny_exchange_rate = get_setting_numeric("cny_exchange_rate", 195.0)

selected_default_date = datetime.strptime(
    st.session_state.get("selected_finance_date", str(date.today())),
    "%Y-%m-%d"
).date()

tabs = st.tabs([
    "대시보드",
    "상품 판정",
    "상품 관리",
    "샘플/구매",
    "매출",
    "지출",
    "재무 달력",
    "월별 손익",
    "설정"
])


# =========================
# 1. 대시보드
# =========================

with tabs[0]:
    st.title("대시보드")
    st.caption("상품 소싱부터 돈 흐름까지 현재 상태를 보는 화면입니다.")

    total_products = len(product_df)

    strong_products = (
        len(product_df[product_df["judgment"] == "강력 후보"])
        if not product_df.empty and "judgment" in product_df.columns
        else 0
    )

    sample_candidates = (
        len(product_df[product_df["status"] == "샘플 구매 후보"])
        if not product_df.empty and "status" in product_df.columns
        else 0
    )

    purchase_total = (
        purchase_df["total_purchase_cost"].sum()
        if not purchase_df.empty and "total_purchase_cost" in purchase_df.columns
        else 0
    )

    expense_total = (
        expense_df["amount"].sum()
        if not expense_df.empty and "amount" in expense_df.columns
        else 0
    )

    sales_total = (
        sales_df["gross_sales"].sum()
        if not sales_df.empty and "gross_sales" in sales_df.columns
        else 0
    )

    sales_profit = (
        sales_df["net_profit"].sum()
        if not sales_df.empty and "net_profit" in sales_df.columns
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 상품 후보", total_products)
    c2.metric("강력 후보", strong_products)
    c3.metric("샘플 후보", sample_candidates)
    c4.metric("총매출", format_won(sales_total))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("판매 순이익", format_won(sales_profit))
    c6.metric("샘플/구매 누적", format_won(purchase_total))
    c7.metric("일반 지출 누적", format_won(expense_total))
    c8.metric("현금 기준 잔액", format_won(sales_total - purchase_total - expense_total))

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("담당자별 상품 수")
        if product_df.empty or "manager_name" not in product_df.columns:
            st.info("상품 데이터가 없습니다.")
        else:
            manager_count = product_df["manager_name"].fillna("미지정").value_counts().reset_index()
            manager_count.columns = ["담당자", "상품 수"]
            st.dataframe(manager_count, use_container_width=True, hide_index=True)

    with right:
        st.subheader("진행상태별 상품 수")
        if product_df.empty or "status" not in product_df.columns:
            st.info("상품 데이터가 없습니다.")
        else:
            status_count = product_df["status"].fillna("미지정").value_counts().reset_index()
            status_count.columns = ["진행상태", "상품 수"]
            st.dataframe(status_count, use_container_width=True, hide_index=True)


# =========================
# 2. 상품 판정
# =========================

with tabs[1]:
    st.title("상품 판정")
    st.caption("도매 원가와 쿠팡 판매가를 넣고 상품성을 판정한 뒤, 결과를 확인하고 저장합니다.")

    with st.form("product_create_form"):
        st.subheader("상품 기본 정보")

        a1, a2 = st.columns(2)

        with a1:
            product_name = st.text_input("상품명")
            category = st.selectbox("카테고리", CATEGORY_OPTIONS)
            source_site = st.selectbox("소싱처/도매처", SOURCE_SITE_OPTIONS)
            source_url = st.text_input("도매 상품 URL", placeholder="링크가 없으면 비워두세요")
            product_url_coupang = st.text_input("쿠팡 비교 URL", placeholder="링크가 없으면 비워두세요")
            memo = st.text_area("파트너/등록 메모")

        with a2:
            status = st.selectbox("진행상태", STATUS_OPTIONS, index=0)
            competition_level = st.selectbox("경쟁 강도", ["낮음", "보통", "높음"], index=1)
            risk_items = st.multiselect("리스크 체크", RISK_OPTIONS)
            final_memo = st.text_area("최종 메모")
            reject_reason = st.selectbox("탈락 사유", REJECT_REASON_OPTIONS)

        st.subheader("도매 원가/배송비")

        b1, b2, b3 = st.columns(3)

        with b1:
            source_currency = st.selectbox("원가 통화", SOURCE_CURRENCY_OPTIONS)
            yuan_price = st.number_input("도매 원가", min_value=0.0, value=10.0, step=1.0)

            if source_currency == "중국 위안화(CNY)":
                exchange_rate = st.number_input(
                    "환율/환산값",
                    min_value=0.0,
                    value=float(cny_exchange_rate),
                    step=1.0,
                    disabled=True
                )
                st.caption("설정 탭의 중국 위안화 환율이 자동 적용됩니다.")

            elif source_currency == "한국 원화(KRW)":
                exchange_rate = st.number_input(
                    "환율/환산값",
                    min_value=0.0,
                    value=1.0,
                    step=1.0,
                    disabled=True
                )
                st.caption("국내 도매 상품은 원화 기준이라 1로 계산합니다.")

            else:
                exchange_rate = st.number_input(
                    "환율/환산값 직접 입력",
                    min_value=0.0,
                    value=float(cny_exchange_rate),
                    step=1.0
                )

        with b2:
            china_shipping_krw = st.number_input("중국/도매처 내 배송비", min_value=0.0, value=0.0, step=100.0)
            intl_shipping_krw = st.number_input("국제배송/관부가세", min_value=0.0, value=2500.0, step=100.0)

        with b3:
            domestic_shipping_krw = st.number_input("국내택배/포장비", min_value=0.0, value=3000.0, step=100.0)
            extra_cost_krw = st.number_input("기타 비용", min_value=0.0, value=500.0, step=100.0)

        st.subheader("쿠팡 판매 조건")

        c1, c2, c3 = st.columns(3)

        with c1:
            coupang_price = st.number_input("쿠팡 판매가", min_value=0.0, value=19900.0, step=100.0)
            target_margin_rate = st.number_input("목표 마진율 %", min_value=0.0, value=20.0, step=1.0)

        with c2:
            coupang_fee_rate = st.number_input("쿠팡 수수료 %", min_value=0.0, value=10.8, step=0.1)
            ad_rate = st.number_input("광고비 %", min_value=0.0, value=5.0, step=0.5)

        with c3:
            vat_rate = st.number_input("세금 보수 반영 %", min_value=0.0, value=5.0, step=0.5)
            risk_rate = st.number_input("반품/불량 리스크 %", min_value=0.0, value=3.0, step=0.5)

        calculate_product_button = st.form_submit_button("상품 판정하기")

    if calculate_product_button:
        if not product_name.strip():
            st.error("상품명은 반드시 입력해야 합니다.")
        else:
            calc = calculate_product(
                yuan_price,
                exchange_rate,
                china_shipping_krw,
                intl_shipping_krw,
                domestic_shipping_krw,
                extra_cost_krw,
                coupang_price,
                coupang_fee_rate,
                ad_rate,
                vat_rate,
                risk_rate,
                target_margin_rate,
                competition_level,
                risk_items
            )

            current_name = current_user_name()

            st.session_state["pending_product_result"] = {
                "user_name": current_name,
                "manager_name": current_name,
                "created_by": current_name,
                "updated_by": current_name,
                "reviewed_by": current_name if final_memo or status != "1차 수집" else "",
                "product_name": product_name.strip(),
                "category": category,
                "source_site": source_site,
                "source_currency": source_currency,
                "source_url": source_url.strip(),
                "status": status,
                "product_url_1688": source_url.strip(),
                "product_url_coupang": product_url_coupang.strip(),
                "memo": memo,
                "final_memo": final_memo,
                "reject_reason": reject_reason,
                "yuan_price": yuan_price,
                "exchange_rate": exchange_rate,
                "china_shipping_krw": china_shipping_krw,
                "intl_shipping_krw": intl_shipping_krw,
                "domestic_shipping_krw": domestic_shipping_krw,
                "extra_cost_krw": extra_cost_krw,
                "coupang_price": coupang_price,
                "coupang_fee_rate": coupang_fee_rate,
                "ad_rate": ad_rate,
                "vat_rate": vat_rate,
                "risk_rate": risk_rate,
                "target_margin_rate": target_margin_rate,
                "competition_level": competition_level,
                "risk_items": ", ".join(risk_items),
                "updated_at": now_iso(),
                **calc
            }

    if "pending_product_result" in st.session_state:
        result = st.session_state["pending_product_result"]

        st.divider()
        st.subheader("판정 결과")

        r1, r2, r3, r4 = st.columns(4)

        r1.metric("총 원가/개", format_won(result["total_unit_cost"]))
        r2.metric("실수령 예상/개", format_won(result["net_sales"]))
        r3.metric("순이익/개", format_won(result["profit"]))
        r4.metric("마진율", f"{result['margin_rate']:.1f}%")

        r5, r6, r7, r8 = st.columns(4)

        r5.metric("ROI", f"{result['roi_rate']:.1f}%")
        r6.metric("판정", result["judgment"])
        r7.metric("소싱처", result["source_site"])
        r8.metric("담당자", result["manager_name"])

        if result["judgment"] == "강력 후보":
            st.success("강력 후보입니다. 단, 인증/상표권/배송 리스크는 추가 확인하세요.")
        elif result["judgment"] == "검토 가능":
            st.info("검토 가능합니다. 경쟁 상품 리뷰 수, 판매자 수, 상세페이지 난이도를 추가 확인하세요.")
        elif result["judgment"] == "보류":
            st.warning("보류입니다. 원가를 낮추거나 판매가/구성을 바꾸지 않으면 애매합니다.")
        else:
            st.error("탈락입니다. 현재 조건으로는 수익성이 낮습니다.")

        db = get_supabase_client()

        duplicate_list = []
        if db is not None:
            duplicate_list = duplicate_warnings(
                db,
                result.get("source_url", ""),
                result.get("product_url_coupang", "")
            )

        allow_duplicate_save = False

        if duplicate_list:
            st.warning("중복 가능성이 있습니다. 같은 상품인지 확인하세요.")
            for item in duplicate_list:
                st.write(f"- {item}")

            allow_duplicate_save = st.checkbox("중복 가능성이 있어도 저장합니다.")
        else:
            allow_duplicate_save = True

        col_save, col_clear = st.columns(2)

        with col_save:
            if st.button("이 판정 저장하기"):
                db = get_db()

                if db is not None:
                    if duplicate_list and not allow_duplicate_save:
                        st.error("중복 가능성이 있습니다. 저장하려면 체크박스를 먼저 눌러주세요.")
                    else:
                        try:
                            db.table("product_records").insert(result).execute()
                            st.success(f"저장 완료. 담당자: {current_user_name()}, 판정: {result['judgment']}")
                            del st.session_state["pending_product_result"]
                            st.rerun()
                        except Exception as e:
                            st.error("상품 저장 실패")
                            st.code(str(e))

        with col_clear:
            if st.button("판정 결과 지우기"):
                del st.session_state["pending_product_result"]
                st.rerun()


# =========================
# 3. 상품 관리
# =========================

with tabs[2]:
    st.title("상품 관리")
    st.caption("상품 검색, 필터, 수정, 삭제를 처리합니다.")

    if product_df.empty:
        st.info("아직 상품이 없습니다.")
    else:
        filter1, filter2, filter3, filter4 = st.columns(4)

        with filter1:
            keyword = st.text_input("검색", placeholder="상품명/메모")

        with filter2:
            judgment_filter = st.selectbox("판정", ["전체", "강력 후보", "검토 가능", "보류", "탈락"])

        with filter3:
            status_filter = st.selectbox("상태", ["전체"] + STATUS_OPTIONS)

        with filter4:
            if "manager_name" in product_df.columns:
                manager_values = ["전체"] + sorted([
                    x for x in product_df["manager_name"].dropna().unique().tolist()
                    if x
                ])
            else:
                manager_values = ["전체"]

            manager_filter = st.selectbox("담당자", manager_values)

        filtered = product_df.copy()

        if keyword:
            mask = pd.Series(False, index=filtered.index)

            for col in ["product_name", "memo", "final_memo", "risk_items"]:
                if col in filtered.columns:
                    mask = mask | filtered[col].fillna("").astype(str).str.contains(keyword, case=False, na=False)

            filtered = filtered[mask]

        if judgment_filter != "전체" and "judgment" in filtered.columns:
            filtered = filtered[filtered["judgment"] == judgment_filter]

        if status_filter != "전체" and "status" in filtered.columns:
            filtered = filtered[filtered["status"] == status_filter]

        if manager_filter != "전체" and "manager_name" in filtered.columns:
            filtered = filtered[filtered["manager_name"] == manager_filter]

        sort_option = st.selectbox("정렬", ["최근순", "ROI 높은 순", "마진율 높은 순", "순이익 높은 순"])

        if sort_option == "ROI 높은 순" and "roi_rate" in filtered.columns:
            filtered = filtered.sort_values("roi_rate", ascending=False)
        elif sort_option == "마진율 높은 순" and "margin_rate" in filtered.columns:
            filtered = filtered.sort_values("margin_rate", ascending=False)
        elif sort_option == "순이익 높은 순" and "profit" in filtered.columns:
            filtered = filtered.sort_values("profit", ascending=False)
        elif "created_at" in filtered.columns:
            filtered = filtered.sort_values("created_at", ascending=False)

        show_cols = [
            "id",
            "created_at",
            "product_name",
            "category",
            "source_site",
            "source_currency",
            "source_url",
            "manager_name",
            "created_by",
            "updated_by",
            "status",
            "judgment",
            "coupang_price",
            "total_unit_cost",
            "profit",
            "margin_rate",
            "roi_rate",
            "competition_level",
            "risk_items",
            "reject_reason",
            "memo",
            "final_memo",
            "product_url_coupang"
        ]

        show_cols = [col for col in show_cols if col in filtered.columns]
        show_df(filtered[show_cols], "상품관리")

        st.divider()
        st.subheader("선택 상품 수정/삭제")

        product_map = {product_label(row): row for row in products}
        selected_label = st.selectbox("상품 선택", list(product_map.keys()))
        selected = product_map[selected_label]

        with st.form("product_edit_form"):
            e1, e2 = st.columns(2)

            with e1:
                edit_name = st.text_input("상품명", value=as_text(selected.get("product_name")))

                edit_category = st.selectbox(
                    "카테고리",
                    CATEGORY_OPTIONS,
                    index=safe_select_index(CATEGORY_OPTIONS, as_text(selected.get("category"), "기타"), 0)
                )

                edit_source_site = st.selectbox(
                    "소싱처/도매처",
                    SOURCE_SITE_OPTIONS,
                    index=safe_select_index(SOURCE_SITE_OPTIONS, as_text(selected.get("source_site"), "1688"), 0)
                )
                
                edit_status = st.selectbox(
                    "진행상태",
                    STATUS_OPTIONS,
                    index=safe_select_index(STATUS_OPTIONS, as_text(selected.get("status"), "1차 수집"), 0)
                )

                edit_reject = st.selectbox(
                    "탈락 사유",
                    REJECT_REASON_OPTIONS,
                    index=safe_select_index(REJECT_REASON_OPTIONS, as_text(selected.get("reject_reason"), ""), 0)
                )

                edit_competition = st.selectbox(
                    "경쟁 강도",
                    ["낮음", "보통", "높음"],
                    index=safe_select_index(["낮음", "보통", "높음"], as_text(selected.get("competition_level"), "보통"), 1)
                )

            with e2:
                edit_url_1688 = st.text_input(
                    "도매 상품 URL",
                    value=as_text(selected.get("source_url") or selected.get("product_url_1688"))
                )
                
                edit_url_coupang = st.text_input("쿠팡 URL", value=as_text(selected.get("product_url_coupang")))

                edit_risk = st.multiselect(
                    "리스크 체크",
                    RISK_OPTIONS,
                    default=[
                        x for x in split_risk_items(selected.get("risk_items"))
                        if x in RISK_OPTIONS
                    ]
                )

                edit_memo = st.text_area("메모", value=as_text(selected.get("memo")))
                edit_final_memo = st.text_area("최종 메모", value=as_text(selected.get("final_memo")))

            st.subheader("숫자 수정")

            n1, n2, n3 = st.columns(3)

            with n1:
                edit_source_currency = st.selectbox(
                    "원가 통화",
                    SOURCE_CURRENCY_OPTIONS,
                    index=safe_select_index(
                        SOURCE_CURRENCY_OPTIONS,
                        as_text(selected.get("source_currency"), "중국 위안화(CNY)"),
                        0
                    )
                )

                edit_yuan = st.number_input(
                    "도매 원가",
                    min_value=0.0,
                    value=as_float(selected.get("yuan_price"), 0),
                    step=1.0
                )

                if edit_source_currency == "중국 위안화(CNY)":
                    edit_exchange = st.number_input(
                        "환율/환산값",
                        min_value=0.0,
                        value=float(cny_exchange_rate),
                        step=1.0,
                        disabled=True
                    )

                elif edit_source_currency == "한국 원화(KRW)":
                    edit_exchange = st.number_input(
                        "환율/환산값",
                        min_value=0.0,
                        value=1.0,
                        step=1.0,
                        disabled=True
                    )

                else:
                    edit_exchange = st.number_input(
                        "환율/환산값 직접 입력",
                        min_value=0.0,
                        value=as_float(selected.get("exchange_rate"), float(cny_exchange_rate)),
                        step=1.0
                    )

            with n2:
                edit_china_ship = st.number_input("중국 내 배송비", min_value=0.0, value=as_float(selected.get("china_shipping_krw"), 0), step=100.0)
                edit_intl_ship = st.number_input("국제배송/관부가세", min_value=0.0, value=as_float(selected.get("intl_shipping_krw"), 2500), step=100.0)
                edit_domestic_ship = st.number_input("국내택배/포장비", min_value=0.0, value=as_float(selected.get("domestic_shipping_krw"), 3000), step=100.0)
                edit_extra = st.number_input("기타 비용", min_value=0.0, value=as_float(selected.get("extra_cost_krw"), 500), step=100.0)

            with n3:
                edit_coupang_price = st.number_input("쿠팡 판매가", min_value=0.0, value=as_float(selected.get("coupang_price"), 19900), step=100.0)
                edit_fee = st.number_input("쿠팡 수수료 %", min_value=0.0, value=as_float(selected.get("coupang_fee_rate"), 10.8), step=0.1)
                edit_ad = st.number_input("광고비 %", min_value=0.0, value=as_float(selected.get("ad_rate"), 5.0), step=0.5)
                edit_vat = st.number_input("세금 보수 반영 %", min_value=0.0, value=as_float(selected.get("vat_rate"), 5.0), step=0.5)
                edit_risk_rate = st.number_input("반품/불량 리스크 %", min_value=0.0, value=as_float(selected.get("risk_rate"), 3.0), step=0.5)
                edit_target = st.number_input("목표 마진율 %", min_value=0.0, value=as_float(selected.get("target_margin_rate"), 20.0), step=1.0)

            submit_edit = st.form_submit_button("수정 저장")

        if submit_edit:
            db = get_db()

            if db is not None:
                calc = calculate_product(
                    edit_yuan,
                    edit_exchange,
                    edit_china_ship,
                    edit_intl_ship,
                    edit_domestic_ship,
                    edit_extra,
                    edit_coupang_price,
                    edit_fee,
                    edit_ad,
                    edit_vat,
                    edit_risk_rate,
                    edit_target,
                    edit_competition,
                    edit_risk
                )

                current_name = current_user_name()

                update_row = {
                    "product_name": edit_name,
                    "category": edit_category,
                    "source_site": edit_source_site,
                    "source_currency": edit_source_currency,
                    "source_url": edit_url_1688.strip(),
                    "status": edit_status,
                    "reject_reason": edit_reject,
                    "competition_level": edit_competition,
                    "product_url_1688": edit_url_1688.strip(),
                    "product_url_coupang": edit_url_coupang.strip(),
                    "risk_items": ", ".join(edit_risk),
                    "memo": edit_memo,
                    "final_memo": edit_final_memo,
                    "yuan_price": edit_yuan,
                    "exchange_rate": edit_exchange,
                    "china_shipping_krw": edit_china_ship,
                    "intl_shipping_krw": edit_intl_ship,
                    "domestic_shipping_krw": edit_domestic_ship,
                    "extra_cost_krw": edit_extra,
                    "coupang_price": edit_coupang_price,
                    "coupang_fee_rate": edit_fee,
                    "ad_rate": edit_ad,
                    "vat_rate": edit_vat,
                    "risk_rate": edit_risk_rate,
                    "target_margin_rate": edit_target,
                    "manager_name": current_name,
                    "updated_by": current_name,
                    "reviewed_by": current_name,
                    "updated_at": now_iso(),
                    **calc
                }

                try:
                    db.table("product_records").update(update_row).eq("id", selected["id"]).execute()
                    st.success(f"수정 완료. 담당자: {current_name}")
                    st.rerun()
                except Exception as e:
                    st.error("수정 실패")
                    st.code(str(e))

        confirm_delete = st.checkbox("선택 상품 삭제 확인")

        if st.button("선택 상품 삭제", disabled=not confirm_delete):
            db = get_db()

            if db is not None:
                try:
                    db.table("product_records").delete().eq("id", selected["id"]).execute()
                    st.success("삭제 완료")
                    st.rerun()
                except Exception as e:
                    st.error("삭제 실패")
                    st.code(str(e))


# =========================
# 4. 샘플/구매 관리
# =========================

with tabs[3]:
    st.title("샘플/구매 관리")
    st.caption("샘플 구매, 사입, 배송, 입고 상태와 샘플비를 기록합니다.")

    product_options = ["직접 입력"]
    product_lookup = {}

    for row in products:
        label = product_label(row)
        product_options.append(label)
        product_lookup[label] = row

    with st.form("purchase_form"):
        p1, p2 = st.columns(2)

        with p1:
            selected_product_label = st.selectbox("연결 상품", product_options)

            if selected_product_label == "직접 입력":
                purchase_product_name = st.text_input("상품명 직접 입력")
                purchase_product_id = None
            else:
                selected_product = product_lookup[selected_product_label]
                purchase_product_name = selected_product.get("product_name", "")
                purchase_product_id = selected_product.get("id")
                st.write(f"상품명: **{purchase_product_name}**")

            purchase_date = st.date_input("구매일", value=selected_default_date)
            supplier = st.text_input("구매처", value="도매처")
            purchase_status = st.selectbox("구매 상태", PURCHASE_STATUS_OPTIONS)

        with p2:
            purchase_quantity = st.number_input("수량", min_value=0, value=1, step=1)
            product_amount = st.number_input("상품 금액", min_value=0.0, value=0.0, step=100.0)
            china_shipping = st.number_input("중국 배송비", min_value=0.0, value=0.0, step=100.0)
            intl_shipping = st.number_input("국제 배송비", min_value=0.0, value=0.0, step=100.0)
            purchase_other_cost = st.number_input("기타 비용", min_value=0.0, value=0.0, step=100.0)

        sample_rating = st.selectbox("샘플 평가", ["", "좋음", "보통", "나쁨", "판매 보류"])
        purchase_memo = st.text_area("구매/샘플 메모")
        add_purchase = st.form_submit_button("구매 기록 저장")

    if add_purchase:
        db = get_db()

        if db is not None:
            total_purchase_cost = product_amount + china_shipping + intl_shipping + purchase_other_cost
            current_name = current_user_name()

            row = {
                "product_id": purchase_product_id,
                "product_name": purchase_product_name,
                "purchase_date": str(purchase_date),
                "supplier": supplier,
                "quantity": purchase_quantity,
                "product_amount": product_amount,
                "china_shipping": china_shipping,
                "intl_shipping": intl_shipping,
                "other_cost": purchase_other_cost,
                "total_purchase_cost": total_purchase_cost,
                "purchase_status": purchase_status,
                "sample_rating": sample_rating,
                "manager_name": current_name,
                "created_by": current_name,
                "updated_by": current_name,
                "memo": purchase_memo,
                "updated_at": now_iso()
            }

            try:
                db.table("purchase_records").insert(row).execute()
                st.success(f"구매 기록 저장 완료. 담당자: {current_name}")
                st.rerun()
            except Exception as e:
                st.error("구매 기록 저장 실패")
                st.code(str(e))

    st.subheader("구매 내역")
    show_df(purchase_df, "구매내역")

    if purchases:
        purchase_map = {record_label(row): row for row in purchases}
        purchase_delete_label = st.selectbox("삭제할 구매 기록", list(purchase_map.keys()))
        purchase_selected = purchase_map[purchase_delete_label]

        confirm_purchase_delete = st.checkbox("구매 기록 삭제 확인")

        if st.button("선택 구매 기록 삭제", disabled=not confirm_purchase_delete):
            db = get_db()

            if db is not None:
                try:
                    db.table("purchase_records").delete().eq("id", purchase_selected["id"]).execute()
                    st.success("구매 기록 삭제 완료")
                    st.rerun()
                except Exception as e:
                    st.error("삭제 실패")
                    st.code(str(e))


# =========================
# 5. 매출 관리
# =========================

with tabs[4]:
    st.title("매출 관리")
    st.caption("쿠팡 등 판매 매출과 상품별 순이익을 수동 기록합니다.")

    product_options = ["직접 입력"]
    product_lookup = {}

    for row in products:
        label = product_label(row)
        product_options.append(label)
        product_lookup[label] = row

    with st.form("sales_form"):
        s1, s2 = st.columns(2)

        with s1:
            selected_product_label = st.selectbox("판매 상품", product_options, key="sales_product_select")

            if selected_product_label == "직접 입력":
                sale_product_name = st.text_input("상품명 직접 입력", key="sale_product_name")
            else:
                selected_product = product_lookup[selected_product_label]
                sale_product_name = selected_product.get("product_name", "")
                st.write(f"상품명: **{sale_product_name}**")

            sale_date = st.date_input("판매일", value=selected_default_date)
            channel = st.selectbox("판매 채널", SALES_CHANNEL_OPTIONS)
            sale_quantity = st.number_input("판매 수량", min_value=0, value=1, step=1)

        with s2:
            sale_price = st.number_input("개당 판매가", min_value=0.0, value=0.0, step=100.0)
            product_cost = st.number_input("상품 원가 합계", min_value=0.0, value=0.0, step=100.0)
            coupang_fee = st.number_input("수수료 합계", min_value=0.0, value=0.0, step=100.0)
            shipping_cost = st.number_input("배송비 합계", min_value=0.0, value=0.0, step=100.0)
            ad_cost = st.number_input("광고비 합계", min_value=0.0, value=0.0, step=100.0)
            sales_other_cost = st.number_input("기타 차감 합계", min_value=0.0, value=0.0, step=100.0)

        sales_memo = st.text_area("매출 메모")
        add_sale = st.form_submit_button("매출 기록 저장")

    if add_sale:
        db = get_db()

        if db is not None:
            gross_sales = sale_price * sale_quantity
            net_profit = gross_sales - product_cost - coupang_fee - shipping_cost - ad_cost - sales_other_cost
            current_name = current_user_name()

            row = {
                "sale_date": str(sale_date),
                "product_name": sale_product_name,
                "channel": channel,
                "quantity": sale_quantity,
                "sale_price": sale_price,
                "gross_sales": gross_sales,
                "product_cost": product_cost,
                "coupang_fee": coupang_fee,
                "shipping_cost": shipping_cost,
                "ad_cost": ad_cost,
                "other_cost": sales_other_cost,
                "net_profit": net_profit,
                "manager_name": current_name,
                "created_by": current_name,
                "updated_by": current_name,
                "memo": sales_memo,
                "updated_at": now_iso()
            }

            try:
                db.table("sales_records").insert(row).execute()
                st.success(f"매출 기록 저장 완료. 담당자: {current_name}, 순이익: {format_won(net_profit)}")
                st.rerun()
            except Exception as e:
                st.error("매출 기록 저장 실패")
                st.code(str(e))

    st.subheader("매출 내역")
    show_df(sales_df, "매출내역")

    if sales:
        sales_map = {record_label(row): row for row in sales}
        sales_delete_label = st.selectbox("삭제할 매출 기록", list(sales_map.keys()))
        sales_selected = sales_map[sales_delete_label]

        confirm_sales_delete = st.checkbox("매출 기록 삭제 확인")

        if st.button("선택 매출 기록 삭제", disabled=not confirm_sales_delete):
            db = get_db()

            if db is not None:
                try:
                    db.table("sales_records").delete().eq("id", sales_selected["id"]).execute()
                    st.success("매출 기록 삭제 완료")
                    st.rerun()
                except Exception as e:
                    st.error("삭제 실패")
                    st.code(str(e))


# =========================
# 6. 지출 관리
# =========================

with tabs[5]:
    st.title("지출 관리")
    st.caption("샘플비 외 일반 지출, 포장재, 광고비, 소프트웨어 비용 등을 기록합니다.")

    with st.form("expense_form"):
        x1, x2 = st.columns(2)

        with x1:
            expense_date = st.date_input("지출일", value=selected_default_date)
            expense_category = st.selectbox("지출 카테고리", EXPENSE_CATEGORY_OPTIONS)
            description = st.text_input("지출 내용")
            amount = st.number_input("금액", min_value=0.0, value=0.0, step=100.0)

        with x2:
            payment_method = st.selectbox("결제수단", ["카드", "계좌이체", "현금", "기타"])
            related_product = st.text_input("관련 상품")
            receipt_status = st.selectbox("영수증", ["없음", "있음", "확인 필요"])
            expense_memo = st.text_area("지출 메모")

        add_expense = st.form_submit_button("지출 기록 저장")

    if add_expense:
        db = get_db()

        if db is not None:
            current_name = current_user_name()

            row = {
                "expense_date": str(expense_date),
                "category": expense_category,
                "description": description,
                "amount": amount,
                "payment_method": payment_method,
                "related_product": related_product,
                "receipt_status": receipt_status,
                "manager_name": current_name,
                "created_by": current_name,
                "updated_by": current_name,
                "memo": expense_memo,
                "updated_at": now_iso()
            }

            try:
                db.table("expense_records").insert(row).execute()
                st.success(f"지출 기록 저장 완료. 담당자: {current_name}")
                st.rerun()
            except Exception as e:
                st.error("지출 기록 저장 실패")
                st.code(str(e))

    st.subheader("지출 내역")
    show_df(expense_df, "지출내역")

    if expenses:
        expense_map = {record_label(row, name_key="description"): row for row in expenses}
        expense_delete_label = st.selectbox("삭제할 지출 기록", list(expense_map.keys()))
        expense_selected = expense_map[expense_delete_label]

        confirm_expense_delete = st.checkbox("지출 기록 삭제 확인")

        if st.button("선택 지출 기록 삭제", disabled=not confirm_expense_delete):
            db = get_db()

            if db is not None:
                try:
                    db.table("expense_records").delete().eq("id", expense_selected["id"]).execute()
                    st.success("지출 기록 삭제 완료")
                    st.rerun()
                except Exception as e:
                    st.error("삭제 실패")
                    st.code(str(e))

# =========================
# 7. 재무 달력
# =========================

with tabs[6]:
    st.title("재무 달력")
    st.caption("매출은 +, 일반 지출과 샘플/구매 지출은 -로 표시합니다.")

    render_finance_calendar(sales_df, expense_df, purchase_df)


# =========================
# 7. 월별 손익
# =========================

with tabs[7]:
    st.title("월별 손익")
    st.caption("매출, 샘플/구매비, 일반 지출을 월별로 합산합니다. 세무 신고용이 아니라 사업 판단용입니다.")

    monthly = {}

    if not sales_df.empty and "sale_date" in sales_df.columns:
        temp = sales_df.copy()
        temp["월"] = pd.to_datetime(temp["sale_date"], errors="coerce").dt.to_period("M").astype(str)

        sales_group = temp.groupby("월").agg(
            총매출=("gross_sales", "sum"),
            판매순이익=("net_profit", "sum")
        ).reset_index()

        for _, row in sales_group.iterrows():
            month = row["월"]
            if month not in monthly:
                monthly[month] = {
                    "월": month,
                    "총매출": 0,
                    "판매순이익": 0,
                    "샘플구매비": 0,
                    "일반지출": 0
                }

            monthly[month]["총매출"] += float(row["총매출"])
            monthly[month]["판매순이익"] += float(row["판매순이익"])

    if not purchase_df.empty and "purchase_date" in purchase_df.columns:
        temp = purchase_df.copy()
        temp["월"] = pd.to_datetime(temp["purchase_date"], errors="coerce").dt.to_period("M").astype(str)

        purchase_group = temp.groupby("월").agg(
            샘플구매비=("total_purchase_cost", "sum")
        ).reset_index()

        for _, row in purchase_group.iterrows():
            month = row["월"]
            if month not in monthly:
                monthly[month] = {
                    "월": month,
                    "총매출": 0,
                    "판매순이익": 0,
                    "샘플구매비": 0,
                    "일반지출": 0
                }

            monthly[month]["샘플구매비"] += float(row["샘플구매비"])

    if not expense_df.empty and "expense_date" in expense_df.columns:
        temp = expense_df.copy()
        temp["월"] = pd.to_datetime(temp["expense_date"], errors="coerce").dt.to_period("M").astype(str)

        expense_group = temp.groupby("월").agg(
            일반지출=("amount", "sum")
        ).reset_index()

        for _, row in expense_group.iterrows():
            month = row["월"]
            if month not in monthly:
                monthly[month] = {
                    "월": month,
                    "총매출": 0,
                    "판매순이익": 0,
                    "샘플구매비": 0,
                    "일반지출": 0
                }

            monthly[month]["일반지출"] += float(row["일반지출"])

    if not monthly:
        st.info("아직 매출/구매/지출 데이터가 없습니다.")
    else:
        monthly_df = pd.DataFrame(list(monthly.values()))
        monthly_df = monthly_df.sort_values("월", ascending=False)

        monthly_df["현금기준손익"] = (
            monthly_df["총매출"]
            - monthly_df["샘플구매비"]
            - monthly_df["일반지출"]
        )

        monthly_df["사업판단순이익"] = (
            monthly_df["판매순이익"]
            - monthly_df["일반지출"]
        )

        monthly_df["매출대비순이익률"] = monthly_df.apply(
            lambda row: (row["사업판단순이익"] / row["총매출"] * 100) if row["총매출"] > 0 else 0,
            axis=1
        )

        st.subheader("월별 요약")
        st.dataframe(monthly_df, use_container_width=True, hide_index=True)

        csv_data = monthly_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="월별 손익 CSV 다운로드",
            data=csv_data,
            file_name="monthly_profit_summary.csv",
            mime="text/csv"
        )

        st.divider()

        latest = monthly_df.iloc[0]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("최근 월", latest["월"])
        m2.metric("총매출", format_won(latest["총매출"]))
        m3.metric("사업판단순이익", format_won(latest["사업판단순이익"]))
        m4.metric("순이익률", f"{latest['매출대비순이익률']:.1f}%")

        st.caption("현금기준손익 = 총매출 - 샘플구매비 - 일반지출")
        st.caption("사업판단순이익 = 판매순이익 - 일반지출")


# =========================
# 9. 설정
# =========================

with tabs[8]:
    st.title("설정")
    st.caption("앱 전체에 적용되는 기본값을 관리합니다.")

    st.subheader("환율 설정")

    st.info("중국 위안화(CNY)를 선택한 상품 판정에는 아래 환율이 자동 적용됩니다. 국내 도매 상품은 원화 기준이므로 환율/환산값이 1로 계산됩니다.")

    with st.form("settings_form"):
        new_cny_rate = st.number_input(
            "중국 위안화 환율/환산값",
            min_value=0.0,
            value=float(cny_exchange_rate),
            step=1.0
        )

        save_settings = st.form_submit_button("설정 저장")

    if save_settings:
        ok, error_message = save_setting_numeric(
            "cny_exchange_rate",
            new_cny_rate,
            current_user_name()
        )

        if ok:
            st.success(f"중국 위안화 환율이 {new_cny_rate}로 저장되었습니다.")
            st.rerun()
        else:
            st.error("설정 저장 실패")
            st.code(error_message)
