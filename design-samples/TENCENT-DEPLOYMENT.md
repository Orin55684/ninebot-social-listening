# 腾讯云样品部署记录

部署日期：2026-09-15。

方案 1 重制更新：新增 `blue-v2.js`、`blue-v2.css`，由 `reference.html` 加载。保留 `reference.js` 和 `reference.css` 不变，因此方案 2、3 继续使用原渲染与样式。旧入口文件备份位于服务器 `/tmp/ninebot-blue-v2.4Wn6AG/reference.html.before`（临时备份）。移除入口中的两条 blue-v2 引用并恢复方案标签即可回退，无需修改 Nginx。

样品入口：https://115.159.196.173:8080/listening-demo/

旧版对照：https://115.159.196.173:8080/listening-demo/index.html#compare

## 范围

- 静态目录：`/var/www/listening-demo`，仅包含 `index.html`、`style.css`、`app.js`、`reference.html`、`reference.css`、`reference.js`。
- Nginx 独立片段：`/etc/nginx/snippets/listening-demo-location.conf`。
- 在现有 `/etc/nginx/sites-enabled/ugc-https` 的 443 和 8080 两个 HTTPS server 中各新增一条 include。现有业务路由和 TLS 配置保留。
- 默认页为 `reference.html`，禁止目录索引，添加 noindex。noindex 不等于访问控制：此样品路径公开可读，只能放虚构数据。
- 未上传真实数据、环境配置、模型凭证、SSH 密钥和 Git 元数据。没有新增应用进程、数据库或防火墙规则。

## 验证与限制

配置修改前后均通过 `nginx -t`，使用 reload 生效。公网验证使用正常证书校验，没有忽略 TLS 错误。8080 入口可达；本机直连标准 443 端口超时，未修改安全组或防火墙。

## 回退

部署前配置备份保留在服务器 `/tmp/ninebot-samples.bzEpJg/ugc-https.before`。该路径位于临时目录，不是长期备份。

回退时应先检查部署后是否有其他配置变更；仅撤销两个 listening-demo include，测试通过后 reload。不得直接用旧备份覆盖后续业务变更。撤销 include 即可停止公开服务，静态文件仍保留可恢复。
