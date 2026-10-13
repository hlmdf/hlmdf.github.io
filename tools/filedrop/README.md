# 文件中转站

同一 IP 每天最多上传 100 次；以 Asia/Shanghai 日历日期为准，北京时间零点自动恢复。
计数保存在 usage.json，重启服务不会恢复同一天的额度。首次从旧累计限额升级时，开始新的当日额度；原 usage.json 会先备份。
失败上传会退回对应日期的额度，跨日失败不会扣减或退回新一天的计数。下载不受上传额度限制。
客户端页面每分钟及重新切回页面时刷新额度。

运行 `npm ci`，再 `npm start`。服务监听参数沿用 HOST 和 PORT；服务器 Nginx 对外端口为 HTTPS 5002，服务端口 3001。
部署脚本位于 ../deploy-personal-tools；只更新代码，保留 uploads 和 usage.json。

测试：`node --test daily-quota.test.cjs`。
