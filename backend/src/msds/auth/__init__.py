"""로그인과 권한: 비밀번호 해시, JWT 발급·검증, 사용자 저장소, FastAPI 의존성.

security  비밀번호 해시(argon2)와 access·refresh JWT(HS256)
users     사용자·refresh 토큰 저장소 (PostgreSQL auth 스키마, 시험·파일 모드용 메모리)
deps      current_user(로그인 필수), require_admin(관리자), acting_reviewer(기록에 남길 검토자 이름)
setup     앱 수명에서 인증 설정·저장소를 app.state.auth 에 넣는다
"""
