# 后端接口与数据执行清单（V1）

版本：v1.0
日期：2026-04-17
关联文档：`docs/design/PRD-v1.md`、`docs/design/database.md`

---

## 1. 文档目标

本文档用于把 V1 PRD 转换为后端可执行交付清单，覆盖：

- API 接口范围
- 鉴权与权限边界
- 统计口径落地要求
- 页面到接口的映射
- 开发优先级与验收要点

不再讨论产品范围是否做，而是默认以 `PRD-v1.md` 为准执行。

---

## 2. 后端总体原则

- API 统一使用 REST 风格，路径前缀为 `/api/v1`
- 线上查询主数据源为 SQLite
- JSON 仅作离线审计与回放数据，不直接给前端消费
- 列表页接口只返回列表所需字段
- 详情页接口优先单接口返回整页所需数据
- 搜索使用单一自然语言接口，由后端判断结果路由
- 公开内容接口无需登录
- 搜索接口需要登录

---

## 3. 数据与口径约束

### 3.1 统一实体定义

- `event`：赛事
- `sub event`：赛事项目
- `match`：具体比赛

接口命名、字段命名、返回结构必须遵守上述层级，不混用“赛事 / 项目 / 比赛”。

### 3.2 排名口径

- 当前排名：女子单打最新一期排名名次
- 当前积分：女子单打最新一期排名积分

### 3.3 统计口径

- 胜率：全量历史 `match` 胜率
- 外战 / 内战：按国家判断
- `events` 总数：按 `event` 去重统计
- 三大赛：`event_categories.sort_order` 在 `1-5`
- 七大赛：`event_categories.sort_order` 在 `1-9`
- 七大赛进决赛次数：包含冠军
- V1 暂不计算世界冠军总数

### 3.4 缺失值规则

- 数据缺失时返回可识别空状态，不用 `0` 伪装缺失
- 搜索无结果与“不支持的问题类型”要明确区分

---

## 4. 鉴权与账号能力

### 4.1 公开接口

以下内容接口默认公开：

- 首页摘要接口
- 排名页接口
- 对比页接口
- 球员详情接口
- 赛事列表接口
- 赛事详情接口
- 比赛详情接口

### 4.2 受限接口

以下接口必须登录后访问：

- 自然语言搜索接口

### 4.3 账号接口

V1 账号能力包括：

- 注册
- 登录
- 登出
- 获取当前用户信息

规则：

- 注册：邮箱 + 用户名 + 验证码 + 密码 + 确认密码
- 登录：邮箱 + 密码
- 登录态记住 30 天
- 暂不支持修改密码、找回密码、第三方登录

### 4.4 账号校验规则

- 用户名长度 20 以内
- 用户名字符仅允许中英文和数字
- 以下错误返回具体原因：
  - 验证码校验错误
  - 用户名重复
  - 密码不一致
  - 邮箱已被注册
- 其他错误返回通用提示，详细日志写服务端

---

## 5. API 清单

## 5.1 首页赛事日程接口

### 接口
`GET /api/v1/home/calendar`

### 用途
为首页月历图提供重点赛事列表。

### 后端职责

- 按赛事分类过滤“重点赛事”
- 返回赛事列表，不直接返回月历图结构
- 保留前端自行组装月历图的灵活性

### 建议参数

- `year`
- `month` 可选

### 最少返回字段

- `event_id`
- `name`
- `name_zh`
- `start_date`
- `end_date`
- `event_category_id`
- `category_name_zh`

---

## 5.2 首页 Top 20 排名接口

### 接口
`GET /api/v1/home/rankings`

### 用途
为首页 Top 20 排名模块提供摘要数据。

### 最少返回字段

- `player_id`
- `slug`
- `rank`
- `rank_change`
- `name`
- `name_zh`
- `avatar`
- `country_code`
- `points`

---

## 5.3 排名页接口

### 接口
`GET /api/v1/rankings`

### 用途
提供女子单打最新一期排名列表。

### 建议参数

- `category=women_singles`
- `sort_by=points|win_rate|head_to_head_count`

### 返回要求

- 只返回列表展示所需字段
- 排序切换后仍返回原始排名和积分
- 支持前端点击进入球员 profile

### 最少返回字段

- `player_id`
- `slug`
- `rank`
- `rank_change`
- `name`
- `name_zh`
- `avatar`
- `country_code`
- `points`
- `sort_value`

---

## 5.4 双球员对比接口

### 接口
`GET /api/v1/compare`

### 参数

- `player_a`
- `player_b`

### 用途
承接排名页勾选两名球员后的结构化对比页。

### 返回内容

- 两名球员基础信息
- 核心统计指标
- 历史交手汇总统计
- 历史交手记录列表

### 核心统计字段

- `rank`
- `points`
- `win_rate`
- `foreign_win_rate`
- `domestic_win_rate`
- `major_top3_titles`
- `major_top7_titles`
- `event_count`
- `major_top7_final_count`

### 历史交手汇总

- 总交手次数
- 双方交手胜场
- 双方交手胜率

### 历史交手记录列表字段

- `match_id`
- `date`
- `event_name`
- `round`
- `score`

说明：

- 不强制返回获胜方，前端可根据比分判断
- 返回记录需按时间倒序排好

---

## 5.5 球员详情接口

### 接口
`GET /api/v1/players/{slug}`

### 用途
单接口返回球员详情页完整数据。

### 返回结构

#### 顶部信息

- 头像
- 中文名
- 英文名
- 国家
- 当前排名
- 当前积分

#### 核心统计

- 排名
- 积分
- 胜率
- 外战胜率
- 内战胜率
- 三大赛冠军总数
- 七大赛冠军总数
- `events` 总数
- 七大赛进决赛次数

#### 最近比赛

- 固定最近 3 场 `match`
- 每条至少包括：
  - `match_id`
  - `event_name`
  - `date`
  - `opponent_name`
  - `score`
  - `is_win`

#### 比赛记录

- 以 `events list` 返回
- 每条至少包括：
  - `event_id`
  - `event_name`
  - `date`
  - `sub_event_name`
  - `result_round`

#### Top 3 对手

- 每条至少包括：
  - `opponent_slug`
  - `opponent_name`
  - `head_to_head_count`
  - `win_rate`
  - `last_match_date`

---

## 5.6 赛事列表接口

### 接口
`GET /api/v1/events`

### 参数

- `year`

### 用途
按年份浏览赛事列表。

### 规则

- 最多支持回溯到 2014
- V1 不支持复杂筛选

### 最少返回字段

- `event_id`
- `name`
- `name_zh`
- `start_date`
- `end_date`

---

## 5.7 赛事详情接口

### 接口
`GET /api/v1/events/{eventId}`

### 参数

- `sub_event` 可选

### 用途
返回赛事详情页完整数据。

### 默认规则

- 普通赛事默认女单
- 团体赛默认女子团体

### 返回内容

#### 基础信息

- `event_id`
- `event_name`
- `event_name_zh`
- `start_date`
- `end_date`

#### sub event 列表

- 当前赛事存在的 `sub event`
- 每个 `sub event` 的最终冠军
- 当前选中的 `sub event`
- 无数据的 `sub event` 也要返回，由前端置灰

#### 当前 sub event 对战图数据

- 正赛节点
- 晋级路径
- 可跳转 `match_id`

---

## 5.8 比赛详情接口

### 接口
`GET /api/v1/matches/{matchId}`

### 用途
返回单场比赛详情页数据。

### 最少返回字段

- `match_id`
- `event_id`
- `event_name`
- `sub_event_name`
- `round`
- `stage`
- `date`
- `player_a`
- `player_b`
- `country_a`
- `country_b`
- `score`
- `games`
- `winner`

---

## 5.9 搜索接口

### 接口
`POST /api/v1/search`

### 鉴权
必须登录后访问。

### 请求字段

- `query`

### 结果类型

- `redirect_compare`
- `search_result`
- `mixed_result`
- `unsupported`

### 路由规则

1. 如果问题可完全映射到结构化对比指标，返回 `redirect_compare`
2. 如果问题不能结构化承接，返回 `search_result`
3. 如果问题一部分可结构化、一部分不可，则返回 `mixed_result`
4. 如果问题类型不在 V1 支持范围内，返回 `unsupported`

### mixed_result 返回要求

- 第一部分：结构化结果
- 第二部分：搜索结果表格

---

## 5.10 注册接口

### 接口
`POST /api/v1/auth/register`

### 字段

- `email`
- `username`
- `verification_code`
- `password`
- `confirm_password`

---

## 5.11 登录接口

### 接口
`POST /api/v1/auth/login`

### 字段

- `email`
- `password`

### 登录态

- 记住 30 天

---

## 5.12 登出接口

### 接口
`POST /api/v1/auth/logout`

---

## 5.13 当前用户接口

### 接口
`GET /api/v1/auth/me`

### 返回字段

- `username`
- `email`
- `created_at`

---

## 5.14 反馈日志接口

### 接口
`POST /api/v1/feedback`

### 用途
接收页面反馈 / 上报请求。

### V1 最少字段

- 当前页面的接口请求参数

### 行为要求

- 成功后返回可供前端展示“已反馈”的成功状态
- V1 不做去重和频控

---

## 6. 页面与接口映射

- 首页
  - `GET /api/v1/home/calendar`
  - `GET /api/v1/home/rankings`
- 排名页
  - `GET /api/v1/rankings`
- 对比页
  - `GET /api/v1/compare`
- 球员详情页
  - `GET /api/v1/players/{slug}`
- 赛事列表页
  - `GET /api/v1/events?year=...`
- 赛事详情页
  - `GET /api/v1/events/{eventId}`
- 比赛详情页
  - `GET /api/v1/matches/{matchId}`
- 搜索结果页
  - `POST /api/v1/search`
- 账号页
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
- 反馈
  - `POST /api/v1/feedback`

---

## 7. 开发优先级

### P0

- 首页两个摘要接口
- 排名页接口
- 对比接口
- 球员详情接口
- 赛事列表接口
- 赛事详情接口
- 比赛详情接口
- 注册 / 登录 / 登出 / me
- 搜索接口骨架

### P1

- 搜索问题类型识别与结果路由
- mixed_result 返回结构
- 反馈日志接口
- 限流与未授权拦截

---

## 8. 基础风控要求

- 注册接口限流
- 登录接口限流
- 搜索接口限流
- 未登录访问搜索接口返回明确未授权
- 出现限流时给前端明确提示
- 页面和接口具备基础防爬策略

---

## 9. 验收清单

- 所有内容页接口可稳定访问
- 搜索接口登录后可用，未登录不可用
- 列表页接口只返回列表字段
- 详情页接口一次可返回整页数据
- 统计口径与 PRD 第 10 章一致
- 三大赛 / 七大赛口径基于 `event_categories.sort_order`
- mixed_result 可同时返回结构化结果和搜索结果表格
- 注册 / 登录错误提示符合约定
- 限流和未授权处理正确
