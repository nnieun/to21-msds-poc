"""API 시험용 로그인 사용자. 로그인 자체를 보는 시험은 test_auth_api.py 에 있다.

    app = sign_in(create_app(...))          # 관리자 '김검수'로 로그인한 것처럼
    app = sign_in(create_app(...), READER)  # 일반 검토자로
"""
from msds.auth.deps import current_user, signed_in_as
from msds.auth.users import User

TESTER = User(1, "tester", "김검수", "admin")
READER = User(2, "reader", "이검수", "reviewer")


def sign_in(app, user: User = TESTER):
    app.dependency_overrides[current_user] = signed_in_as(user)
    return app
