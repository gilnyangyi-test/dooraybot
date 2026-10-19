from fastapi import APIRouter, Request

from api.common import pack

router = APIRouter()


# =========================================================
# 메뉴
# =========================================================
MENU_SECTIONS = {
    "커피": [
        "에스프레소",
        "아메리카노",
        "카페라떼",
        "카푸치노",
        "바닐라라떼",
        "돌체라떼",
        "시나몬라떼",
        "헤이즐넛라떼",
        "카라멜마키야토",
        "카페모카",
        "피치프레소",
        "더치커피",
    ],
        "스무디": [
        "딸기주스",
        "바나나주스",
        "레몬요거트 스무디",
        "블루베리요거트 스무디",
        "딸기 요거트 스무디",
        "딸기 바나나 스무디",
    ],
    "음료": [
        "그린티 라떼",
        "오곡라떼",
        "고구마라떼",
        "로얄밀크티라떼",
        "초콜릿라떼",
        "리얼자몽티",
        "리얼레몬티",
        "진저레몬티",
        "매실차",
        "오미자차",
        "자몽에이드",
        "레몬에이드",
        "진저레몬에이드",
        "스팀우유",
        "사과유자차",
        "페퍼민트",
        "얼그레이",
        "캐모마일",
        "유자민트 릴렉서 티",
        "ICE 케모리치 릴렉서티",
        "배도라지모과차",
        "헛개차",
        "복숭아 아이스티",
        "딸기라떼",
    ],
    "병음료": [
        "분다버그 진저",
        "분다버그 레몬에이드",
        "분다버그 망고",
        "분다버그 자몽",
    ],
}


# =========================================================
# 디카페인 가능 메뉴
# 여기에 있는 메뉴만 "🌙 디카페인 선택" 드롭다운에 노출된다.
# =========================================================
DECAF_MENUS = {
    "에스프레소",
    "아메리카노",
    "카페라떼",
    "카푸치노",
    "바닐라라떼",
    "돌체라떼",
    "시나몬라떼",
    "헤이즐넛라떼",
    "카라멜마키야토",
    "카페모카",
    "피치프레소",
}
DECAF_PREFIX = "디카페인 "


# =========================================================
# 메뉴 드롭다운 블록 색상
# =========================================================
MENU_BLOCK_COLOR = "#F59E0B"


# =========================================================
# "선택안함" 버튼 액션 값 / 선택 현황에 표시될 키
# =========================================================
CLEAR_ACTION_VALUE = "clear"
NO_SELECTION_KEY = "선택안함"
CLOSE_ACTION_VALUE = "투표종료"
REOPEN_ACTION_VALUE = "투표수정"


# =========================================================
# Dooray 사용자 멘션 문자열 생성
# =========================================================
def mention_member(
    tenant_id: str,
    user_id: str,
    label: str = "member",
) -> str:
    return f'(dooray://{tenant_id}/members/{user_id} "{label}")'


# =========================================================
# 버튼 클릭값 가져오기
#
# Dooray 요청에 따라 다음 형태를 모두 처리
# 1. actionValue
# 2. actions[0].value
# =========================================================
def get_action_value(data: dict) -> str:
    action_value = (data.get("actionValue") or "").strip()

    if action_value:
        return action_value

    actions = data.get("actions") or []

    if isinstance(actions, list) and actions:
        first_action = actions[0] or {}
        value = (first_action.get("value") or "").strip()

        if value:
            return value

        # select(드롭다운) 선택값
        selected = (
            first_action.get("selectedOptions")
            or first_action.get("selected_options")
            or []
        )

        if isinstance(selected, list) and selected:
            return ((selected[0] or {}).get("value") or "").strip()

    return ""


# =========================================================
# 기존 메시지에서 선택 현황 읽기
# =========================================================
def parse_status(original: dict) -> dict:
    result = {}

    for attachment in original.get("attachments") or []:
        if attachment.get("title") != "선택 현황":
            continue

        for field in attachment.get("fields") or []:
            key = (field.get("title") or "").strip()
            raw_value = (field.get("value") or "").strip()

            if not key:
                continue

            # 최초 안내 문구는 실제 투표 데이터에서 제외
            if key == "아직 투표 없음":
                continue

            voters = [
                line.strip()
                for line in raw_value.split("\n")
                if line.strip() and line.strip() != "-"
            ]

            if voters:
                result[key] = voters

    return result


# =========================================================
# 투표 현황을 Dooray field 형식으로 변환
# =========================================================
def status_fields(status: dict) -> list[dict]:
    if not status:
        return [
            {
                "title": "아직 투표 없음",
                "value": "첫 투표를 기다리는 중!",
                "short": False,
            }
        ]

    return [
        {
            "title": menu_name,
            "value": "\n".join(voters),
            "short": True,
        }
        for menu_name, voters in status.items()
    ]


# =========================================================
# 선택 현황 attachment 생성
# =========================================================
def status_attachment(fields=None) -> dict:
    return {
        "title": "선택 현황",
        "fields": fields
        or [
            {
                "title": "아직 투표 없음",
                "value": "첫 투표를 기다리는 중!",
                "short": False,
            }
        ],
    }


# =========================================================
# 메뉴별 선택 가능한 온도 (ICE / HOT)
# =========================================================
def menu_temperatures(section: str, menu: str) -> list[str]:
    allow_hot = (
        section not in ["스무디", "병음료"]
        and menu not in ["복숭아 아이스티", "딸기라떼"]
        and "요거트" not in menu
        and not menu.startswith("ICE ")
    )

    return ["ICE", "HOT"] if allow_hot else ["ICE"]


# =========================================================
# 드롭다운 표시 폭 계산 / 맞추기
#
# 한글 등 전각 문자는 2칸, 그 외는 1칸으로 계산한다.
# 드롭다운 안의 모든 텍스트를 가장 긴 텍스트 폭에 맞춰
# 뒤쪽을 공백으로 채워, 폭이 가장 긴 메뉴명 기준으로 잡히게 한다.
# (U+3000 전각 공백은 HTML 공백 병합/trim 대상이 아니라 유지됨)
# =========================================================
FULL_WIDTH_SPACE = "　"
HALF_WIDTH_SPACE = " "


def display_width(text: str) -> int:
    return sum(2 if ord(char) > 0x2E80 else 1 for char in text)


def pad_to_width(text: str, width: int) -> str:
    gap = width - display_width(text)

    if gap <= 0:
        return text

    return text + FULL_WIDTH_SPACE * (gap // 2) + HALF_WIDTH_SPACE * (gap % 2)


# =========================================================
# 드롭다운 생성
#
# option value 형식: vote|섹션|메뉴|온도
# 디카페인은 메뉴명 앞에 DECAF_PREFIX를 붙여서
# "디카페인 아메리카노 (ICE)" 키로 집계된다.
#
# 표시 텍스트
# - ICE만 있는 메뉴: 메뉴명만 표시
# - ICE/HOT 둘 다 있는 메뉴: "메뉴 ICE" / "메뉴 HOT"
# =========================================================
def menu_select(
    name: str,
    placeholder: str,
    section: str,
    menus: list[str],
    prefix: str = "",
) -> dict:
    options = []

    for menu in menus:
        temperatures = menu_temperatures(section, menu)
        menu_name = f"{prefix}{menu}"

        for temperature in temperatures:
            options.append(
                {
                    "text": (
                        menu_name
                        if len(temperatures) == 1
                        else f"{menu_name} {temperature}"
                    ),
                    "value": f"vote|{section}|{menu_name}|{temperature}",
                }
            )

    width = max(
        display_width(text)
        for text in [placeholder] + [option["text"] for option in options]
    )

    for option in options:
        option["text"] = pad_to_width(option["text"], width)

    return {
        "name": name,
        "type": "select",
        "text": pad_to_width(placeholder, width),
        "options": options,
    }


# =========================================================
# 메뉴 드롭다운 블록 생성
#
# 섹션 제목 줄 없이 모든 섹션의 select를 한 블록에 모아
# 메시지 높이를 줄인다. 섹션 이름은 드롭다운 placeholder로 표시.
# 커피 섹션 뒤에는 디카페인 드롭다운을 하나 더 붙인다.
# =========================================================
def menu_select_block() -> list[dict]:
    actions = []

    for section, menus in MENU_SECTIONS.items():
        actions.append(
            menu_select(f"vote::{section}", section, section, menus)
        )

        decaf_menus = [menu for menu in menus if menu in DECAF_MENUS]

        if decaf_menus:
            actions.append(
                menu_select(
                    f"vote::{section}::decaf",
                    "디카페인",
                    section,
                    decaf_menus,
                    DECAF_PREFIX,
                )
            )

    return [
        {
            "callbackId": "coffee-poll",
            "actions": actions,
            "color": MENU_BLOCK_COLOR,
        }
    ]


# =========================================================
# "선택안함" 버튼 블록 생성
#
# Dooray 버튼은 더블클릭 이벤트를 전달하지 않으므로,
# 같은 버튼 재클릭 시 토글 취소되는 것과 별개로
# 명시적으로 선택을 지울 수 있는 버튼을 제공한다.
# =========================================================
# =========================================================
# 하단 컨트롤 버튼 (선택안함, 투표 종료, 투표 삭제) 생성
# =========================================================
def control_button_block() -> list[dict]:
    return [
        {
            "callbackId": "coffee-poll",
            "actions": [
                {
                    "name": "clear",
                    "type": "button",
                    "text": f"❌ {NO_SELECTION_KEY}",
                    "value": CLEAR_ACTION_VALUE,
                },
                {
                    "name": "close",
                    "type": "button",
                    "text": "🏁 투표 종료",
                    "value": CLOSE_ACTION_VALUE,
                }
            ],
            "color": "#9CA3AF",
        }
    ]




# =========================================================
# 사용자의 기존 선택을 모두 제거한 status를 반환
#
# 반환값: (제거 후 status, 이번에 지운 값에 user_tag가 있었는지)
# =========================================================
def remove_user_votes(status: dict, user_tag: str) -> dict:
    for current_key in list(status.keys()):
        voters = status.get(current_key) or []

        remaining_voters = [
            voter
            for voter in voters
            if voter != user_tag
        ]

        if remaining_voters:
            status[current_key] = remaining_voters
        else:
            del status[current_key]

    return status


# =========================================================
# 갱신된 status를 반영한 최종 응답 메시지 생성
#
# 드롭다운 블록을 원본에서 복사하지 않고 새로 만들어 보내서,
# 한 목록에서 선택하면 다른 목록의 기존 선택 표시가 초기화되게 한다.
# =========================================================
def rebuild_poll_message(original: dict, status: dict):
    new_attachments = []
    new_attachments.extend(menu_select_block())
    new_attachments.extend(control_button_block())
    new_attachments.append(status_attachment(status_fields(status)))

    return pack(
        {
            "responseType": "inChannel",
            "replaceOriginal": True,
            "text": (
                original.get("text")
                or "☕ 커피 투표를 시작합니다!"
            ),
            "attachments": new_attachments,
        }
    )


# =========================================================
# 최초 커피 투표 메시지 생성
# =========================================================
def create_coffee_poll():
    attachments = []

    section_order = list(MENU_SECTIONS.keys())

    attachments.extend(menu_select_block())
    attachments.extend(control_button_block())
    attachments.append(status_attachment())

    return pack(
        {
            "responseType": "inChannel",
            "replaceOriginal": False,
            "text": "☕ 커피 투표를 시작합니다!",
            "attachments": attachments,
        }
    )


# =========================================================
# 버튼 클릭 처리 (메뉴 선택)
#
# - 선택한 메뉴로 투표 등록 (기존 선택은 자동 해제)
# - 같은 메뉴를 다시 골라도 취소되지 않음
#   (취소는 "선택안함" 버튼으로)
# =========================================================
def handle_coffee_action(
    data: dict,
    action_value: str,
):
    original = data.get("originalMessage") or {}
    user = data.get("user") or {}
    tenant = data.get("tenant") or {}

    user_id = str(user.get("id") or "user")
    tenant_id = str(tenant.get("id") or "tenant")

    # vote|섹션|메뉴|온도
    parts = action_value.split("|", 3)

    if len(parts) != 4:
        print("[INVALID ACTION VALUE]", action_value)
        return pack({})

    _, section, menu, temperature = parts

    selected_key = f"{menu} ({temperature})"

    # 기존 투표 현황 읽기
    status = parse_status(original)

    # 현재 사용자 멘션
    user_tag = mention_member(
        tenant_id=tenant_id,
        user_id=user_id,
    )

    # -----------------------------------------------------
    # 사용자당 전체 메뉴 중 하나만 선택 가능
    # 사용자의 기존 선택을 모두 제거
    # -----------------------------------------------------
    status = remove_user_votes(status, user_tag)

    # -----------------------------------------------------
    # 선택한 메뉴에 현재 사용자 추가
    # (같은 메뉴를 다시 골라도 취소되지 않고 그대로 유지)
    # -----------------------------------------------------
    status.setdefault(selected_key, [])
    status[selected_key].append(user_tag)

    print(
        "[COFFEE VOTE]",
        {
            "section": section,
            "menu": menu,
            "temperature": temperature,
            "user_id": user_id,
            "status": status,
        },
    )

    return rebuild_poll_message(original, status)


# =========================================================
# "선택안함" 버튼 클릭 처리
#
# 다른 메뉴 버튼과 동일하게 취급한다.
# - 처음 클릭: 기존 메뉴 선택을 해제하고 "선택안함"으로 등록
#   (선택 현황에 "선택안함" 항목으로 노출됨)
# - 이미 "선택안함"을 고른 상태에서 다시 클릭:
#   토글 취소되어 완전히 미선택 상태(투표 없음)로 돌아감
# =========================================================
def handle_clear_action(data: dict):
    original = data.get("originalMessage") or {}
    user = data.get("user") or {}
    tenant = data.get("tenant") or {}

    user_id = str(user.get("id") or "user")
    tenant_id = str(tenant.get("id") or "tenant")

    status = parse_status(original)

    user_tag = mention_member(
        tenant_id=tenant_id,
        user_id=user_id,
    )

    # 이미 "선택안함" 상태였는지 (토글 취소 판단)
    already_no_selection = user_tag in (
        status.get(NO_SELECTION_KEY) or []
    )

    # 사용자의 기존 선택(메뉴든 "선택안함"이든)을 전부 제거
    status = remove_user_votes(status, user_tag)

    if already_no_selection:
        # 같은 버튼 재클릭 → 완전한 미선택 상태로 되돌림
        print(
            "[COFFEE VOTE NO-SELECTION TOGGLE OFF]",
            {"user_id": user_id},
        )
    else:
        # "선택안함"을 새로 등록
        status.setdefault(NO_SELECTION_KEY, [])

        if user_tag not in status[NO_SELECTION_KEY]:
            status[NO_SELECTION_KEY].append(user_tag)

        print(
            "[COFFEE VOTE NO-SELECTION]",
            {
                "user_id": user_id,
                "status": status,
            },
        )

    return rebuild_poll_message(original, status)

def handle_close_action(data: dict):
    original = data.get("originalMessage") or {}
    
    # 1. 기존 투표 현황 데이터를 읽어옵니다.
    status = parse_status(original)
    
    # 2. 투표 현황 데이터를 화면에 뿌려줄 필드(updated_fields) 형식으로 변환합니다.
    updated_fields = status_fields(status)

    # 3. 최종 결과와 수정 버튼을 표시합니다.
    return pack({
        "responseType": "inChannel",
        "replaceOriginal": True,
        "text": "🏁 커피 투표가 종료되었습니다! (최종 결과)",
        "attachments": [
            status_attachment(updated_fields),
            {
                "callbackId": "coffee-poll",
                "actions": [{
                    "name": "reopen",
                    "type": "button",
                    "text": "✏️ 수정",
                    "value": REOPEN_ACTION_VALUE,
                }],
            },
        ]
    })
    
def handle_reopen_action(data: dict):
    """기존 투표 결과를 유지하면서 공용 투표를 다시 연다."""
    original = data.get("originalMessage") or {}
    if not any(
        action.get("value") == REOPEN_ACTION_VALUE
        for attachment in original.get("attachments") or []
        for action in attachment.get("actions") or []
    ):
        return pack({})
    status = parse_status(original)
    attachments = []
    attachments.extend(menu_select_block())
    attachments.extend(control_button_block())
    attachments.append(status_attachment(status_fields(status)))
    return pack({
        "responseType": "inChannel",
        "replaceOriginal": True,
        "text": "☕ 커피 투표 수정 중입니다. 메뉴를 눌러 선택을 변경해주세요.",
        "attachments": attachments,
    })


# =========================================================
# Dooray 커피 투표 단일 URL
#
# 최초 슬래시 명령과 버튼 클릭 요청을 같은 URL에서 처리
#
# Request URL:
# https://dooray-bot.vercel.app/dooray/coffee
# =========================================================
@router.post("/dooray/coffee")
@router.post("/dooray/command")
async def coffee_endpoint(req: Request):
    data = await req.json()
    print("[COFFEE REQUEST]", data)

    action_value = get_action_value(data)

    # "선택안함" 버튼 클릭
    if action_value == CLEAR_ACTION_VALUE:
        return handle_clear_action(data=data)

    if action_value == REOPEN_ACTION_VALUE:
        return handle_reopen_action(data=data)

    if action_value == CLOSE_ACTION_VALUE:
        return handle_close_action(data=data)

    # 메뉴 드롭다운 선택
    if action_value.startswith("vote|"):
        return handle_coffee_action(
            data=data,
            action_value=action_value,
        )

    # 최초 슬래시 커맨드 요청
    return create_coffee_poll()
