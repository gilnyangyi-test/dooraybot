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
# 섹션 스타일
# =========================================================
SECTION_STYLE = {
    "추천메뉴": {
        "emoji": "✨",
        "color": "#7C3AED",
    },
    "스무디": {
        "emoji": "🍓",
        "color": "#06B6D4",
    },
    "커피": {
        "emoji": "☕",
        "color": "#F59E0B",
    },
    "음료": {
        "emoji": "🥤",
        "color": "#10B981",
    },
    "병음료": {
        "emoji": "🧃",
        "color": "#EF4444",
    },
}


# =========================================================
# "선택안함" 버튼 액션 값 / 선택 현황에 표시될 키
# =========================================================
CLEAR_ACTION_VALUE = "clear"
NO_SELECTION_KEY = "선택안함"
CLOSE_ACTION_VALUE = "투표종료"


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
# =========================================================
def get_action_value(data: dict) -> str:
    action_value = (data.get("actionValue") or "").strip()

    if action_value:
        return action_value

    actions = data.get("actions") or []

    if isinstance(actions, list) and actions:
        first_action = actions[0] or {}
        return (first_action.get("value") or "").strip()

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
            "short": False,
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
# 섹션별 메뉴 버튼 생성 (5개씩 분할 배치)
# =========================================================
def section_block_buttons(section: str) -> list[dict]:
    style = SECTION_STYLE.get(
        section,
        {
            "emoji": "•",
            "color": "#4757C4",
        },
    )

    all_actions = []

    for menu in MENU_SECTIONS[section]:
        # ICE 버튼
        all_actions.append(
            {
                "name": f"vote::{section}",
                "type": "button",
                "text": f"{menu} (ICE)",
                "value": f"vote|{section}|{menu}|ICE",
            }
        )

        # HOT 버튼 생성 조건
        allow_hot = (
            section not in ["스무디", "병음료"]
            and menu not in ["복숭아 아이스티", "딸기라떼"]
            and "요거트" not in menu
            and not menu.startswith("ICE ")
        )

        if allow_hot:
            all_actions.append(
                {
                    "name": f"vote::{section}",
                    "type": "button",
                    "text": f"{menu} (HOT)",
                    "value": f"vote|{section}|{menu}|HOT",
                }
            )

    # 5개씩 슬라이스하여 개별 Attachment 블록 생성
    chunk_size = 5
    blocks = []

    for i in range(0, len(all_actions), chunk_size):
        chunk = all_actions[i : i + chunk_size]
        block = {
            "callbackId": "coffee-poll",
            "actions": chunk,
            "color": style["color"],
        }

        # 첫 번째 블록에만 섹션 제목 표시
        if i == 0:
            block["title"] = f"{style['emoji']}  {section}"

        blocks.append(block)

    return blocks


# =========================================================
# 하단 컨트롤 버튼 (선택안함, 투표 종료) 생성
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
                },
            ],
            "color": "#9CA3AF",
        }
    ]


# =========================================================
# 사용자의 기존 선택을 모두 제거한 status를 반환
# =========================================================
def remove_user_votes(status: dict, user_tag: str) -> dict:
    for current_key in list(status.keys()):
        voters = status.get(current_key) or []

        remaining_voters = [
            voter for voter in voters if voter != user_tag
        ]

        if remaining_voters:
            status[current_key] = remaining_voters
        else:
            del status[current_key]

    return status


# =========================================================
# 갱신된 status를 반영한 최종 응답 메시지 생성
# =========================================================
def rebuild_poll_message(original: dict, status: dict):
    updated_fields = status_fields(status)

    new_attachments = []
    status_replaced = False

    for attachment in original.get("attachments") or []:
        if attachment.get("title") == "선택 현황":
            new_attachments.append(status_attachment(updated_fields))
            status_replaced = True
        else:
            new_attachments.append(attachment)

    if not status_replaced:
        new_attachments.append(status_attachment(updated_fields))

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

    for section in section_order:
        attachments.extend(section_block_buttons(section))

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

    parts = action_value.split("|", 3)

    if len(parts) != 4:
        print("[INVALID ACTION VALUE]", action_value)
        return pack({})

    _, section, menu, temperature = parts
    selected_key = f"{menu} ({temperature})"

    status = parse_status(original)

    user_tag = mention_member(
        tenant_id=tenant_id,
        user_id=user_id,
    )

    already_selected = user_tag in (status.get(selected_key) or [])

    status = remove_user_votes(status, user_tag)

    if already_selected:
        print(
            "[COFFEE VOTE TOGGLE OFF]",
            {
                "section": section,
                "menu": menu,
                "temperature": temperature,
                "user_id": user_id,
            },
        )
    else:
        status.setdefault(selected_key, [])

        if user_tag not in status[selected_key]:
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

    already_no_selection = user_tag in (
        status.get(NO_SELECTION_KEY) or []
    )

    status = remove_user_votes(status, user_tag)

    if already_no_selection:
        print(
            "[COFFEE VOTE NO-SELECTION TOGGLE OFF]",
            {"user_id": user_id},
        )
    else:
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


# =========================================================
# "투표 종료" 버튼 클릭 처리
# =========================================================
def handle_close_action(data: dict):
    original = data.get("originalMessage") or {}

    status = parse_status(original)
    updated_fields = status_fields(status)

    return pack(
        {
            "responseType": "inChannel",
            "replaceOriginal": True,
            "text": "🏁 커피 투표가 종료되었습니다! (최종 결과)",
            "attachments": [status_attachment(updated_fields)],
        }
    )


# =========================================================
# Dooray 라우터 엔드포인트
# =========================================================
@router.post("/dooray/coffee")
@router.post("/dooray/command")
async def coffee_endpoint(req: Request):
    data = await req.json()
    print("[COFFEE REQUEST]", data)

    action_value = get_action_value(data)

    if action_value == CLEAR_ACTION_VALUE:
        return handle_clear_action(data=data)

    if action_value == CLOSE_ACTION_VALUE:
        return handle_close_action(data=data)

    if action_value.startswith("vote|"):
        return handle_coffee_action(
            data=data,
            action_value=action_value,
        )

    return create_coffee_poll()
