"""Read form field metadata through the existing server-side Douban session. No posts."""
import json
from html.parser import HTMLParser
import urllib.request
import server


class Fields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag not in ("input", "textarea", "select") or not attrs.get("name"):
            return
        field = {key: attrs[key] for key in ("name", "type", "maxlength") if key in attrs}
        if attrs.get("type") == "checkbox" and attrs.get("value") in ("1", "0", "on", "true", "false", "T", "F"):
            field["value"] = attrs["value"]
        self.fields.append(field)


if __name__ == "__main__":
    session = server.load_douban_session()
    if not session:
        raise SystemExit("未保存豆瓣登录，请先在片单页面登录豆瓣。")
    opener, jar = server.opener_from_cookies(session["cookies"])
    try:
        for url in ("https://movie.douban.com/subject/1292052/",
                    "https://movie.douban.com/j/subject/1292052/interest?interest=collect"):
            response = opener.open(urllib.request.Request(url, headers={"User-Agent": server.DOUBAN_UA,
                                   "Referer": "https://movie.douban.com/subject/1292052/"}), timeout=20)
            raw = response.read().decode("utf-8", "replace")
        data = json.loads(raw) if raw.lstrip().startswith("{") else {}
        markup = data.get("html", raw)
        parser = Fields()
        parser.feed(markup)
        print(json.dumps({"fields": parser.fields, "has_private_label": "仅自己可见" in markup,
                          "has_350_label": "350" in markup}, ensure_ascii=False, indent=2))
    except Exception:
        raise SystemExit("未取得豆瓣表单，请确认豆瓣登录仍有效；没有提交评价或修改任何记录。")
