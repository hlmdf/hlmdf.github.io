"""Interactive password setup; secrets never go in shell history or output."""
import getpass
import os
from pathlib import Path
import secrets
from werkzeug.security import generate_password_hash
from server import atomic_json

def password_is_valid(password):
    return isinstance(password, str) and password != ""


if __name__ == "__main__":
    password = getpass.getpass("设置提醒工具密码: ")
    if not password_is_valid(password):
        raise SystemExit("密码不能为空")
    if getpass.getpass("再次输入密码: ") != password:
        raise SystemExit("两次密码不一致，未修改配置")
    path = Path(os.environ.get("REMINDER_AUTH_FILE", str(Path(__file__).resolve().parent / "auth.json")))
    atomic_json(path, {"password_hash": generate_password_hash(password), "secret_key": secrets.token_hex(32)})
    print("登录配置已保存。若服务正在运行，请重启 reminder-tool 服务。")
