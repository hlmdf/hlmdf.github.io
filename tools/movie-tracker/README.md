# 我的片单

前端位于 ../../public/movies/index.html，随个人主页发布到 GitHub Pages；后端为 server.py，部署在 /opt/movie-tracker。
后端监听 127.0.0.1:8001，Nginx 在 HTTPS 8000 转发。沿用现有 movie-tracker systemd 服务。

登录后点击“修改管理密码”，验证当前管理密码并确认新密码。密码没有长度或字符要求，只不能为空。
修改成功后所有管理登录令牌失效，需要用新密码重新登录。只修改 config.json，不修改豆瓣密码或 douban_session.json。

搜索添加时，已有豆瓣条目显示“已添加过”以及片单状态，并阻止重复点击添加。
优先比较豆瓣 subject ID；手工添加、缺少豆瓣链接的条目按片名、年份和类型匹配，不会混淆同名但不同豆瓣 ID 的条目。

测试：`python -m unittest -v test_password.py`，`node test_frontend.cjs`。
个人密码、豆瓣登录状态和 movies.json 不提交 Git，也不放入部署包。
