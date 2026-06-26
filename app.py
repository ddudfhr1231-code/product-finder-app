import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from supabase import create_client
except Exception:
    create_client = None


st.set_page_config(
    page_title="1688 → 쿠팡 상품 판정",
    page_icon="📦",
    layout="wide"
)


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

    for i in range(1, 6):
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


def login_screen():
    st.title("1688 → 쿠팡 상품 판정 웹앱")
    st.caption("1688 원가, 배송비, 쿠팡 판매가를 넣고 마진/ROI 기준으로 상품성을 판단합니다.")

    accounts = load_accounts()

    if not accounts:
        st.error("Streamlit Secrets에 USER1_ID / USER1_PW가 없습니다.")
        st.info("Streamlit Advanced settings → Secrets에 로그인 정보를 먼저 넣어주세요.")
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


def format_won(value):
    try:
        return f"{int(round(value)):,}원"
    except Exception:
        return "0원"


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()


st.sidebar.title("메뉴")
st.sidebar.write(f"로그인: **{st.session_state.get('user_name', '')}**")

if st.sidebar.button("로그아웃"):
    st.session_state.clear()
    st.rerun()


st.title("1688 → 쿠팡 상품 판정")
st.caption("※ 이 계산기는 1차 상품 필터링용입니다. 실제 세금, 반품률, 광고비, 쿠팡 정책에 따라 결과는 달라질 수 있습니다.")

tab1, tab2 = st.tabs(["상품 판정", "저장 내역"])


with tab1:
    st.subheader("1. 상품 기본 정보")

    with st.form("product_form"):
        col1, col2 = st.columns(2)

        with col1:
            product_name = st.text_input("상품명", placeholder="예: 차량용 송풍기, 세차 브러쉬 세트")
            product_url_1688 = st.text_input("1688 상품 URL", placeholder="https://...")
            product_url_coupang = st.text_input("쿠팡 비교 상품 URL", placeholder="https://...")
            memo = st.text_area("메모", placeholder="특징, 경쟁상품, 주의사항 등")

        with col2:
            competition_level = st.selectbox(
                "경쟁 강도",
                ["낮음", "보통", "높음"],
                index=1
            )

            risk_items = st.multiselect(
                "리스크 체크",
                [
                    "파손 위험",
                    "전기/배터리 제품",
                    "KC 인증 필요 가능성",
                    "부피 큼",
                    "반품률 높을 가능성",
                    "브랜드/상표권 위험",
                    "쿠팡 경쟁 심함",
                    "상세페이지 만들기 어려움"
                ]
            )

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

        result = {
            "user_name": st.session_state.get("user_name", ""),
            "product_name": product_name,
            "product_url_1688": product_url_1688,
            "product_url_coupang": product_url_coupang,
            "memo": memo,
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
            "total_unit_cost": float(total_unit_cost),
            "net_sales": float(net_sales),
            "profit": float(profit),
            "margin_rate": float(margin_rate),
            "roi_rate": float(roi_rate),
            "competition_level": competition_level,
            "risk_items": ", ".join(risk_items),
            "judgment": judgment
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

        m5, m6, m7 = st.columns(3)
        m5.metric("ROI", f"{result['roi_rate']:.1f}%")
        m6.metric("경쟁 강도", result["competition_level"])
        m7.metric("최종 판정", result["judgment"])

        if result["judgment"] == "강력 후보":
            st.success("판정: 강력 후보입니다. 단, KC/상표권/배송 리스크는 추가 확인하세요.")
        elif result["judgment"] == "검토 가능":
            st.info("판정: 검토 가능합니다. 상세페이지, 리뷰 수, 경쟁가를 추가로 확인하세요.")
        elif result["judgment"] == "보류":
            st.warning("판정: 보류입니다. 원가를 낮추거나 판매가/구성을 바꾸지 않으면 애매합니다.")
        else:
            st.error("판정: 탈락입니다. 현재 조건으로는 수익성이 낮습니다.")

        with st.expander("계산 상세 보기"):
            st.write({
                "상품 원가 KRW": format_won(result["yuan_price"] * result["exchange_rate"]),
                "중국 내 배송비": format_won(result["china_shipping_krw"]),
                "국제배송/관부가세": format_won(result["intl_shipping_krw"]),
                "국내택배/포장비": format_won(result["domestic_shipping_krw"]),
                "기타 비용": format_won(result["extra_cost_krw"]),
                "차감률 합계": f"{result['coupang_fee_rate'] + result['ad_rate'] + result['vat_rate'] + result['risk_rate']:.1f}%"
            })

        if st.button("이 판정 저장하기"):
            db = get_supabase_client()

            if db is None:
                st.error("Supabase 연결이 안 되어 있습니다. Secrets와 requirements.txt를 확인하세요.")
            else:
                try:
                    db.table("product_records").insert(result).execute()
                    st.success("저장 완료")
                except Exception as e:
                    st.error("저장 실패")
                    st.code(str(e))


with tab2:
    st.subheader("저장 내역")

    db = get_supabase_client()

    if db is None:
        st.warning("Supabase 연결이 안 되어 있어 저장 내역을 불러올 수 없습니다.")
    else:
        try:
            response = (
                db.table("product_records")
                .select("*")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )

            data = response.data or []

            if not data:
                st.info("아직 저장된 상품이 없습니다.")
            else:
                df = pd.DataFrame(data)

                show_columns = [
                    "created_at",
                    "user_name",
                    "product_name",
                    "coupang_price",
                    "total_unit_cost",
                    "profit",
                    "margin_rate",
                    "roi_rate",
                    "competition_level",
                    "judgment",
                    "memo"
                ]

                existing_columns = [col for col in show_columns if col in df.columns]
                st.dataframe(df[existing_columns], use_container_width=True)

        except Exception as e:
            st.error("저장 내역 불러오기 실패")
            st.code(str(e))
