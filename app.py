import streamlit as st
import pandas as pd
from datetime import datetime, timezone

try:
    from supabase import create_client
except Exception:
    create_client = None


st.set_page_config(
    page_title="1688 → 쿠팡 상품 판정",
    page_icon="📦",
    layout="wide"
)


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

JUDGMENT_OPTIONS = [
    "전체",
    "강력 후보",
    "검토 가능",
    "보류",
    "탈락"
]


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
    st.title("1688 → 쿠팡 상품 판정 웹앱")
    st.caption("상품 후보를 찾고, 마진/ROI를 계산하고, 진행상태까지 관리하는 내부용 앱입니다.")

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


def as_text(value, default=""):
    if value is None:
        return default
    return str(value)


def split_risk_items(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def format_won(value):
    try:
        return f"{int(round(float(value))):,}원"
    except Exception:
        return "0원"


def judge_product(margin_rate, roi_rate, profit, competition_level, risk_count, target_margin_rate):
    if profit <= 0:
        return "탈락"

    if margin_rate >= target_margin_rate + 5 and roi_rate >= 30 and competition_level != "높음" and risk_count <= 1:
        return "강력 후보"

    if margin_rate >= target_margin_rate and roi_rate >= 20 and risk_count <= 2:
        return "검토 가능"

    if margin_rate >= 5 and profit > 0:
        return "보류"

    return "탈락"


def calculate_values(
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

    margin_rate = 0
    if coupang_price > 0:
        margin_rate = profit / coupang_price * 100

    roi_rate = 0
    if total_unit_cost > 0:
        roi_rate = profit / total_unit_cost * 100

    judgment = judge_product(
        margin_rate=margin_rate,
        roi_rate=roi_rate,
        profit=profit,
        competition_level=competition_level,
        risk_count=len(risk_items),
        target_margin_rate=target_margin_rate
    )

    return {
        "total_unit_cost": float(total_unit_cost),
        "net_sales": float(net_sales),
        "profit": float(profit),
        "margin_rate": float(margin_rate),
        "roi_rate": float(roi_rate),
        "judgment": judgment
    }


def fetch_records():
    db = get_supabase_client()

    if db is None:
        return []

    try:
        response = (
            db.table("product_records")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []
    except Exception as e:
        st.error("데이터 불러오기 실패")
        st.code(str(e))
        return []


def records_to_df(records):
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    numeric_cols = [
        "coupang_price",
        "total_unit_cost",
        "profit",
        "margin_rate",
        "roi_rate",
        "yuan_price",
        "exchange_rate",
        "china_shipping_krw",
        "intl_shipping_krw",
        "domestic_shipping_krw",
        "extra_cost_krw",
        "coupang_fee_rate",
        "ad_rate",
        "vat_rate",
        "risk_rate",
        "target_margin_rate"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def check_duplicate(db, product_url_1688, product_url_coupang):
    duplicates = []

    try:
        if product_url_1688:
            res = (
                db.table("product_records")
                .select("id, product_name, product_url_1688")
                .eq("product_url_1688", product_url_1688)
                .limit(1)
                .execute()
            )
            if res.data:
                duplicates.append(f"1688 URL 중복: {res.data[0].get('product_name', '')}")

        if product_url_coupang:
            res = (
                db.table("product_records")
                .select("id, product_name, product_url_coupang")
                .eq("product_url_coupang", product_url_coupang)
                .limit(1)
                .execute()
            )
            if res.data:
                duplicates.append(f"쿠팡 URL 중복: {res.data[0].get('product_name', '')}")

    except Exception:
        pass

    return duplicates


def display_table(df):
    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    preferred_cols = [
        "id",
        "created_at",
        "product_name",
        "category",
        "manager_name",
        "user_name",
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
        "product_url_1688",
        "product_url_coupang"
    ]

    existing_cols = [col for col in preferred_cols if col in df.columns]
    show_df = df[existing_cols].copy()

    rename_map = {
        "id": "ID",
        "created_at": "저장일",
        "product_name": "상품명",
        "category": "카테고리",
        "manager_name": "담당자",
        "user_name": "등록자",
        "updated_by": "최근 수정자",
        "status": "진행상태",
        "judgment": "판정",
        "coupang_price": "쿠팡 판매가",
        "total_unit_cost": "총 원가",
        "profit": "순이익",
        "margin_rate": "마진율",
        "roi_rate": "ROI",
        "competition_level": "경쟁 강도",
        "risk_items": "리스크",
        "reject_reason": "탈락 사유",
        "memo": "메모",
        "final_memo": "최종 메모",
        "product_url_1688": "1688 URL",
        "product_url_coupang": "쿠팡 URL"
    }

    show_df = show_df.rename(columns=rename_map)
    st.dataframe(show_df, use_container_width=True, hide_index=True)


def apply_filters(df):
    if df.empty:
        return df

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    with filter_col1:
        keyword = st.text_input("상품명/메모 검색", placeholder="검색어 입력")

    with filter_col2:
        judgment_filter = st.selectbox("판정", JUDGMENT_OPTIONS)

    with filter_col3:
        status_values = ["전체"] + STATUS_OPTIONS
        status_filter = st.selectbox("진행상태", status_values)

    with filter_col4:
        manager_values = ["전체"]
        if "manager_name" in df.columns:
            manager_values += sorted([x for x in df["manager_name"].dropna().unique().tolist() if x])
        manager_filter = st.selectbox("담당자", manager_values)

    filter_col5, filter_col6 = st.columns(2)

    with filter_col5:
        category_values = ["전체"] + CATEGORY_OPTIONS
        category_filter = st.selectbox("카테고리", category_values)

    with filter_col6:
        sort_option = st.selectbox(
            "정렬",
            ["최근 저장순", "ROI 높은 순", "마진율 높은 순", "순이익 높은 순", "쿠팡 판매가 높은 순"]
        )

    filtered = df.copy()

    if keyword:
        keyword_lower = keyword.lower()
        search_cols = ["product_name", "memo", "final_memo", "risk_items"]
        mask = pd.Series(False, index=filtered.index)

        for col in search_cols:
            if col in filtered.columns:
                mask = mask | filtered[col].fillna("").astype(str).str.lower().str.contains(keyword_lower)

        filtered = filtered[mask]

    if judgment_filter != "전체" and "judgment" in filtered.columns:
        filtered = filtered[filtered["judgment"] == judgment_filter]

    if status_filter != "전체" and "status" in filtered.columns:
        filtered = filtered[filtered["status"] == status_filter]

    if manager_filter != "전체" and "manager_name" in filtered.columns:
        filtered = filtered[filtered["manager_name"] == manager_filter]

    if category_filter != "전체" and "category" in filtered.columns:
        filtered = filtered[filtered["category"] == category_filter]

    if sort_option == "ROI 높은 순" and "roi_rate" in filtered.columns:
        filtered = filtered.sort_values("roi_rate", ascending=False)
    elif sort_option == "마진율 높은 순" and "margin_rate" in filtered.columns:
        filtered = filtered.sort_values("margin_rate", ascending=False)
    elif sort_option == "순이익 높은 순" and "profit" in filtered.columns:
        filtered = filtered.sort_values("profit", ascending=False)
    elif sort_option == "쿠팡 판매가 높은 순" and "coupang_price" in filtered.columns:
        filtered = filtered.sort_values("coupang_price", ascending=False)
    elif "created_at" in filtered.columns:
        filtered = filtered.sort_values("created_at", ascending=False)

    return filtered


def get_record_label(record):
    product_name = as_text(record.get("product_name", "상품명 없음"))
    status = as_text(record.get("status", ""))
    judgment = as_text(record.get("judgment", ""))
    manager = as_text(record.get("manager_name", ""))
    record_id = record.get("id", "")

    return f"{record_id} | {product_name} | {status} | {judgment} | 담당자:{manager}"


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()


st.sidebar.title("메뉴")
st.sidebar.write(f"로그인: **{current_user_name()}**")
st.sidebar.caption("저장/수정 시 담당자는 현재 로그인 계정으로 자동 표시됩니다.")

if st.sidebar.button("로그아웃"):
    st.session_state.clear()
    st.rerun()


records = fetch_records()
df = records_to_df(records)


tab_dashboard, tab_product, tab_records, tab_sample, tab_manage = st.tabs(
    ["대시보드", "상품 판정", "저장 내역", "샘플 후보", "관리/수정"]
)


with tab_dashboard:
    st.title("대시보드")
    st.caption("현재 상품 소싱 진행 상황을 한눈에 보는 화면입니다.")

    if df.empty:
        st.info("아직 저장된 상품이 없습니다.")
    else:
        total_count = len(df)
        strong_count = len(df[df["judgment"] == "강력 후보"]) if "judgment" in df.columns else 0
        review_count = len(df[df["judgment"] == "검토 가능"]) if "judgment" in df.columns else 0
        sample_count = len(df[df["status"] == "샘플 구매 후보"]) if "status" in df.columns else 0
        reject_count = len(df[(df["judgment"] == "탈락") | (df["status"] == "탈락")]) if "judgment" in df.columns and "status" in df.columns else 0

        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric("전체 상품", total_count)
        m2.metric("강력 후보", strong_count)
        m3.metric("검토 가능", review_count)
        m4.metric("샘플 후보", sample_count)
        m5.metric("탈락", reject_count)

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("담당자별 상품 수")
            if "manager_name" in df.columns:
                manager_df = df["manager_name"].fillna("미지정").value_counts().reset_index()
                manager_df.columns = ["담당자", "상품 수"]
                st.dataframe(manager_df, use_container_width=True, hide_index=True)

        with col2:
            st.subheader("진행상태별 상품 수")
            if "status" in df.columns:
                status_df = df["status"].fillna("미지정").value_counts().reset_index()
                status_df.columns = ["진행상태", "상품 수"]
                st.dataframe(status_df, use_container_width=True, hide_index=True)

        st.subheader("최근 저장 상품")
        recent_df = df.head(10)
        display_table(recent_df)


with tab_product:
    st.title("1688 → 쿠팡 상품 판정")
    st.caption("상품을 입력하면 마진율, ROI, 판정을 계산하고 저장할 수 있습니다.")

    with st.form("product_form"):
        st.subheader("1. 상품 기본 정보")

        col1, col2 = st.columns(2)

        with col1:
            product_name = st.text_input("상품명", placeholder="예: 차량용 송풍기, 세차 브러쉬 세트")
            category = st.selectbox("카테고리", CATEGORY_OPTIONS)
            product_url_1688 = st.text_input("1688 상품 URL", placeholder="https://...")
            product_url_coupang = st.text_input("쿠팡 비교 상품 URL", placeholder="https://...")
            memo = st.text_area("메모", placeholder="특징, 경쟁상품, 주의사항 등")

        with col2:
            status = st.selectbox("초기 진행상태", STATUS_OPTIONS, index=0)
            competition_level = st.selectbox("경쟁 강도", ["낮음", "보통", "높음"], index=1)
            risk_items = st.multiselect("리스크 체크", RISK_OPTIONS)
            final_memo = st.text_area("최종 메모", placeholder="영록 최종 판단 메모. 처음엔 비워둬도 됩니다.")
            reject_reason = st.selectbox("탈락 사유", REJECT_REASON_OPTIONS)

        st.divider()
        st.subheader("2. 1688 원가/배송비")

        col3, col4, col5 = st.columns(3)

        with col3:
            yuan_price = st.number_input("1688 상품 원가 (위안/개)", min_value=0.0, value=10.0, step=1.0)
            exchange_rate = st.number_input("적용 환율 (원/위안)", min_value=0.0, value=195.0, step=1.0)

        with col4:
            china_shipping_krw = st.number_input("중국 내 배송비 예상 (원/개)", min_value=0.0, value=0.0, step=100.0)
            intl_shipping_krw = st.number_input("국제배송/관부가세 예상 (원/개)", min_value=0.0, value=2500.0, step=100.0)

        with col5:
            domestic_shipping_krw = st.number_input("국내택배/포장비 예상 (원/개)", min_value=0.0, value=3000.0, step=100.0)
            extra_cost_krw = st.number_input("기타 비용 예상 (원/개)", min_value=0.0, value=500.0, step=100.0)

        st.divider()
        st.subheader("3. 쿠팡 판매 조건")

        col6, col7, col8 = st.columns(3)

        with col6:
            coupang_price = st.number_input("쿠팡 판매가 (원)", min_value=0.0, value=19900.0, step=100.0)
            target_margin_rate = st.number_input("목표 마진율 (%)", min_value=0.0, value=20.0, step=1.0)

        with col7:
            coupang_fee_rate = st.number_input("쿠팡 수수료 예상 (%)", min_value=0.0, value=10.8, step=0.1)
            ad_rate = st.number_input("광고비 예상 (%)", min_value=0.0, value=5.0, step=0.5)

        with col8:
            vat_rate = st.number_input("부가세/세금 보수 반영 (%)", min_value=0.0, value=5.0, step=0.5)
            risk_rate = st.number_input("반품/불량 리스크 비용 (%)", min_value=0.0, value=3.0, step=0.5)

        submitted = st.form_submit_button("상품 판정하기")

    if submitted:
        calc = calculate_values(
            yuan_price=yuan_price,
            exchange_rate=exchange_rate,
            china_shipping_krw=china_shipping_krw,
            intl_shipping_krw=intl_shipping_krw,
            domestic_shipping_krw=domestic_shipping_krw,
            extra_cost_krw=extra_cost_krw,
            coupang_price=coupang_price,
            coupang_fee_rate=coupang_fee_rate,
            ad_rate=ad_rate,
            vat_rate=vat_rate,
            risk_rate=risk_rate,
            target_margin_rate=target_margin_rate,
            competition_level=competition_level,
            risk_items=risk_items
        )

        current_name = current_user_name()

        result = {
            "user_name": current_name,
            "manager_name": current_name,
            "created_by": current_name,
            "updated_by": current_name,
            "reviewed_by": current_name if final_memo or status != "1차 수집" else "",
            "product_name": product_name,
            "category": category,
            "status": status,
            "product_url_1688": product_url_1688.strip(),
            "product_url_coupang": product_url_coupang.strip(),
            "memo": memo,
            "final_memo": final_memo,
            "reject_reason": reject_reason,
            "yuan_price": float(yuan_price),
            "exchange_rate": float(exchange_rate),
            "china_shipping_krw": float(china_shipping_krw),
            "intl_shipping_krw": float(intl_shipping_krw),
            "domestic_shipping_krw": float(domestic_shipping_krw),
            "extra_cost_krw": float(extra_cost_krw),
            "coupang_price": float(coupang_price),
            "coupang_fee_rate": float(coupang_fee_rate),
            "ad_rate": float(ad_rate),
            "vat_rate": float(vat_rate),
            "risk_rate": float(risk_rate),
            "target_margin_rate": float(target_margin_rate),
            "competition_level": competition_level,
            "risk_items": ", ".join(risk_items),
            "updated_at": now_iso(),
            **calc
        }

        st.session_state["last_result"] = result

    if "last_result" in st.session_state:
        result = st.session_state["last_result"]

        st.divider()
        st.subheader("판정 결과")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 원가/개", format_won(result["total_unit_cost"]))
        m2.metric("실수령 예상/개", format_won(result["net_sales"]))
        m3.metric("순이익/개", format_won(result["profit"]))
        m4.metric("마진율", f"{result['margin_rate']:.1f}%")

        m5, m6, m7, m8 = st.columns(4)
        m5.metric("ROI", f"{result['roi_rate']:.1f}%")
        m6.metric("경쟁 강도", result["competition_level"])
        m7.metric("판정", result["judgment"])
        m8.metric("담당자", result["manager_name"])

        if result["judgment"] == "강력 후보":
            st.success("강력 후보입니다. 단, 인증/상표권/배송 리스크는 추가 확인하세요.")
        elif result["judgment"] == "검토 가능":
            st.info("검토 가능합니다. 경쟁 상품 리뷰 수, 판매자 수, 상세페이지 난이도를 추가 확인하세요.")
        elif result["judgment"] == "보류":
            st.warning("보류입니다. 원가를 낮추거나 판매가/구성을 바꾸지 않으면 애매합니다.")
        else:
            st.error("탈락입니다. 현재 조건으로는 수익성이 낮습니다.")

        if st.button("이 판정 저장하기"):
            db = get_supabase_client()

            if db is None:
                st.error("Supabase 연결이 안 되어 있습니다.")
            elif not result["product_name"]:
                st.error("상품명은 반드시 입력해야 합니다.")
            else:
                duplicates = check_duplicate(
                    db,
                    result.get("product_url_1688", ""),
                    result.get("product_url_coupang", "")
                )

                if duplicates:
                    st.error("중복 가능성이 있습니다.")
                    for item in duplicates:
                        st.write(f"- {item}")
                    st.warning("중복이 맞다면 저장하지 말고 기존 상품을 관리/수정 탭에서 수정하세요.")
                else:
                    try:
                        db.table("product_records").insert(result).execute()
                        st.success(f"저장 완료. 담당자: {current_user_name()}")
                        del st.session_state["last_result"]
                        st.rerun()
                    except Exception as e:
                        st.error("저장 실패")
                        st.code(str(e))


with tab_records:
    st.title("저장 내역")
    st.caption("상품 후보를 검색, 필터링, 정렬하고 CSV로 백업할 수 있습니다.")

    if df.empty:
        st.info("아직 저장된 상품이 없습니다.")
    else:
        filtered_df = apply_filters(df)

        st.write(f"표시 상품 수: **{len(filtered_df)}개**")

        csv_data = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="CSV 다운로드",
            data=csv_data,
            file_name="product_records.csv",
            mime="text/csv"
        )

        display_table(filtered_df)


with tab_sample:
    st.title("샘플 후보")
    st.caption("실제로 샘플 구매를 검토할 상품만 따로 보는 화면입니다.")

    if df.empty:
        st.info("아직 저장된 상품이 없습니다.")
    else:
        sample_df = df.copy()

        if "status" in sample_df.columns and "judgment" in sample_df.columns:
            sample_df = sample_df[
                (sample_df["status"] == "샘플 구매 후보")
                | (sample_df["judgment"] == "강력 후보")
            ]

        if sample_df.empty:
            st.info("아직 샘플 후보가 없습니다.")
            st.write("관리/수정 탭에서 진행상태를 `샘플 구매 후보`로 바꾸면 여기에 표시됩니다.")
        else:
            sample_df = sample_df.sort_values(["roi_rate", "margin_rate"], ascending=False)

            m1, m2, m3 = st.columns(3)
            m1.metric("샘플 후보 수", len(sample_df))
            m2.metric("평균 마진율", f"{sample_df['margin_rate'].mean():.1f}%" if "margin_rate" in sample_df.columns else "0%")
            m3.metric("평균 ROI", f"{sample_df['roi_rate'].mean():.1f}%" if "roi_rate" in sample_df.columns else "0%")

            display_table(sample_df)


with tab_manage:
    st.title("관리/수정")
    st.caption("저장된 상품을 수정, 상태 변경, 삭제하는 화면입니다. 수정하면 담당자가 현재 로그인 계정으로 바뀝니다.")

    if not records:
        st.info("수정할 상품이 없습니다.")
    else:
        label_map = {get_record_label(record): record for record in records}
        selected_label = st.selectbox("수정할 상품 선택", list(label_map.keys()))
        selected = label_map[selected_label]

        st.divider()
        st.subheader("상품 수정")

        with st.form("edit_form"):
            col1, col2 = st.columns(2)

            with col1:
                edit_product_name = st.text_input("상품명", value=as_text(selected.get("product_name")))
                edit_category = st.selectbox(
                    "카테고리",
                    CATEGORY_OPTIONS,
                    index=CATEGORY_OPTIONS.index(as_text(selected.get("category"), "기타"))
                    if as_text(selected.get("category"), "기타") in CATEGORY_OPTIONS else 0
                )
                edit_status = st.selectbox(
                    "진행상태",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(as_text(selected.get("status"), "1차 수집"))
                    if as_text(selected.get("status"), "1차 수집") in STATUS_OPTIONS else 0
                )
                edit_competition_level = st.selectbox(
                    "경쟁 강도",
                    ["낮음", "보통", "높음"],
                    index=["낮음", "보통", "높음"].index(as_text(selected.get("competition_level"), "보통"))
                    if as_text(selected.get("competition_level"), "보통") in ["낮음", "보통", "높음"] else 1
                )
                edit_reject_reason = st.selectbox(
                    "탈락 사유",
                    REJECT_REASON_OPTIONS,
                    index=REJECT_REASON_OPTIONS.index(as_text(selected.get("reject_reason"), ""))
                    if as_text(selected.get("reject_reason"), "") in REJECT_REASON_OPTIONS else 0
                )

            with col2:
                edit_product_url_1688 = st.text_input("1688 URL", value=as_text(selected.get("product_url_1688")))
                edit_product_url_coupang = st.text_input("쿠팡 URL", value=as_text(selected.get("product_url_coupang")))
                edit_risk_items = st.multiselect(
                    "리스크 체크",
                    RISK_OPTIONS,
                    default=[x for x in split_risk_items(selected.get("risk_items")) if x in RISK_OPTIONS]
                )
                edit_memo = st.text_area("메모", value=as_text(selected.get("memo")))
                edit_final_memo = st.text_area("최종 메모", value=as_text(selected.get("final_memo")))

            st.divider()
            st.subheader("숫자 수정")

            n1, n2, n3 = st.columns(3)

            with n1:
                edit_yuan_price = st.number_input("1688 원가", min_value=0.0, value=as_float(selected.get("yuan_price"), 0), step=1.0)
                edit_exchange_rate = st.number_input("환율", min_value=0.0, value=as_float(selected.get("exchange_rate"), 195), step=1.0)

            with n2:
                edit_china_shipping_krw = st.number_input("중국 내 배송비", min_value=0.0, value=as_float(selected.get("china_shipping_krw"), 0), step=100.0)
                edit_intl_shipping_krw = st.number_input("국제배송/관부가세", min_value=0.0, value=as_float(selected.get("intl_shipping_krw"), 2500), step=100.0)
                edit_domestic_shipping_krw = st.number_input("국내택배/포장비", min_value=0.0, value=as_float(selected.get("domestic_shipping_krw"), 3000), step=100.0)
                edit_extra_cost_krw = st.number_input("기타 비용", min_value=0.0, value=as_float(selected.get("extra_cost_krw"), 500), step=100.0)

            with n3:
                edit_coupang_price = st.number_input("쿠팡 판매가", min_value=0.0, value=as_float(selected.get("coupang_price"), 19900), step=100.0)
                edit_coupang_fee_rate = st.number_input("쿠팡 수수료 %", min_value=0.0, value=as_float(selected.get("coupang_fee_rate"), 10.8), step=0.1)
                edit_ad_rate = st.number_input("광고비 %", min_value=0.0, value=as_float(selected.get("ad_rate"), 5.0), step=0.5)
                edit_vat_rate = st.number_input("세금 보수 반영 %", min_value=0.0, value=as_float(selected.get("vat_rate"), 5.0), step=0.5)
                edit_risk_rate = st.number_input("반품/불량 리스크 %", min_value=0.0, value=as_float(selected.get("risk_rate"), 3.0), step=0.5)
                edit_target_margin_rate = st.number_input("목표 마진율 %", min_value=0.0, value=as_float(selected.get("target_margin_rate"), 20.0), step=1.0)

            update_submitted = st.form_submit_button("수정 저장")

        if update_submitted:
            db = get_supabase_client()

            calc = calculate_values(
                yuan_price=edit_yuan_price,
                exchange_rate=edit_exchange_rate,
                china_shipping_krw=edit_china_shipping_krw,
                intl_shipping_krw=edit_intl_shipping_krw,
                domestic_shipping_krw=edit_domestic_shipping_krw,
                extra_cost_krw=edit_extra_cost_krw,
                coupang_price=edit_coupang_price,
                coupang_fee_rate=edit_coupang_fee_rate,
                ad_rate=edit_ad_rate,
                vat_rate=edit_vat_rate,
                risk_rate=edit_risk_rate,
                target_margin_rate=edit_target_margin_rate,
                competition_level=edit_competition_level,
                risk_items=edit_risk_items
            )

            current_name = current_user_name()

            update_data = {
                "product_name": edit_product_name,
                "category": edit_category,
                "status": edit_status,
                "competition_level": edit_competition_level,
                "reject_reason": edit_reject_reason,
                "product_url_1688": edit_product_url_1688.strip(),
                "product_url_coupang": edit_product_url_coupang.strip(),
                "risk_items": ", ".join(edit_risk_items),
                "memo": edit_memo,
                "final_memo": edit_final_memo,
                "yuan_price": float(edit_yuan_price),
                "exchange_rate": float(edit_exchange_rate),
                "china_shipping_krw": float(edit_china_shipping_krw),
                "intl_shipping_krw": float(edit_intl_shipping_krw),
                "domestic_shipping_krw": float(edit_domestic_shipping_krw),
                "extra_cost_krw": float(edit_extra_cost_krw),
                "coupang_price": float(edit_coupang_price),
                "coupang_fee_rate": float(edit_coupang_fee_rate),
                "ad_rate": float(edit_ad_rate),
                "vat_rate": float(edit_vat_rate),
                "risk_rate": float(edit_risk_rate),
                "target_margin_rate": float(edit_target_margin_rate),
                "manager_name": current_name,
                "updated_by": current_name,
                "reviewed_by": current_name,
                "updated_at": now_iso(),
                **calc
            }

            try:
                db.table("product_records").update(update_data).eq("id", selected["id"]).execute()
                st.success(f"수정 완료. 담당자: {current_name}")
                st.rerun()
            except Exception as e:
                st.error("수정 실패")
                st.code(str(e))

        st.divider()
        st.subheader("상품 삭제")

        st.warning("삭제하면 복구하기 어렵습니다. 중복/테스트/명백한 오입력 상품만 삭제하세요.")

        confirm_delete = st.checkbox("정말 이 상품을 삭제합니다.")
        if st.button("선택 상품 삭제", disabled=not confirm_delete):
            db = get_supabase_client()

            try:
                db.table("product_records").delete().eq("id", selected["id"]).execute()
                st.success("삭제 완료")
                st.rerun()
            except Exception as e:
                st.error("삭제 실패")
                st.code(str(e))
