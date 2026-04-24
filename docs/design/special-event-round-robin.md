# 特殊赛事展示方案：两阶段循环赛

版本：v1.0  
日期：2026-04-24  
适用场景：`event_id=2860` 及后续同类“分阶段循环赛 / 积分榜决出冠军”赛事

---

## 1. 问题背景

当前赛事详情链路默认建立在淘汰赛假设上：

- `sub_events` 的冠军主要来自 `Final`
- `event_draw_matches` 主要用于生成 bracket
- 前端赛事详情页默认展示“冠军 + 对战图”

但 `ITTF Mixed Team World Cup Chengdu 2023`（`event_id=2860`）并非淘汰赛，而是：

1. 第一阶段分组循环赛
2. 前两名进入第二阶段循环赛
3. 第一阶段同组已交手成绩带入第二阶段
4. 最终按第二阶段积分榜确定冠军、亚军、季军和完整排名

因此，若继续沿用“必须有 Final / 必须能画 bracket”的模型，会出现三个问题：

- 无法得到冠亚军结果
- 无法正确展示赛事流程
- 无法呈现真实的团体赛层级，只能看到拆散的 rubber 级比赛

---

## 2. 设计目标

- 不伪造 `Final`、`SemiFinal` 等淘汰赛结构
- 允许赛事详情页支持非 bracket 型赛事
- 允许冠军来源不是 `Final`，而是 standings / override
- 在不破坏现有 knockout 赛事链路的前提下，为特殊赛制增加第二套展示模型

---

## 3. 设计结论

采用“双赛事表现模型”：

- `knockout`
- `staged_round_robin`

对于 `event_id=2860`：

- 不伪造 `Final`
- 不强行生成假 bracket
- 使用 `staged_round_robin` 模式展示

---

## 4. 数据层方案

### 4.1 新增人工覆盖目录

新增目录：

- `data/manual_event_overrides/`

首个文件：

- `data/manual_event_overrides/2860.json`

该文件只存放 ITTF 原始结构无法表达但业务必须知道的赛事语义，不重复保存已有单场比赛明细。

### 4.2 override 文件用途

用于提供：

- 赛事展示模式
- 阶段定义
- 第一阶段分组信息
- 第二阶段参赛队
- 最终排名
- 冠亚季军

### 4.3 `2860.json` 建议结构

```json
{
  "event_id": 2860,
  "presentation_mode": "staged_round_robin",
  "sub_event_type_code": "XT",
  "title": "ITTF Mixed Team World Cup Chengdu 2023",
  "stages": [
    {
      "code": "stage1",
      "name": "Main Draw - Stage 1",
      "name_zh": "第一阶段",
      "format": "group_round_robin",
      "groups": [
        { "code": "Group 1", "name_zh": "第一组", "teams": ["CHN", "HKG", "SWE", "PUR"] },
        { "code": "Group 2", "name_zh": "第二组", "teams": ["GER", "POR", "EGY", "SVK"] },
        { "code": "Group 3", "name_zh": "第三组", "teams": ["JPN", "FRA", "ROU", "USA", "AUS"] },
        { "code": "Group 4", "name_zh": "第四组", "teams": ["KOR", "TPE", "SGP", "IND", "CAN"] }
      ]
    },
    {
      "code": "stage2",
      "name": "Main Draw - Stage 2",
      "name_zh": "第二阶段",
      "format": "round_robin",
      "qualified_teams": ["CHN", "KOR", "JPN", "SWE", "FRA", "GER", "TPE", "SVK"],
      "carry_over_from_stage1": true
    }
  ],
  "final_standings": [
    { "rank": 1, "team_code": "CHN" },
    { "rank": 2, "team_code": "KOR" },
    { "rank": 3, "team_code": "JPN" },
    { "rank": 4, "team_code": "SWE" },
    { "rank": 5, "team_code": "FRA" },
    { "rank": 6, "team_code": "GER" },
    { "rank": 7, "team_code": "TPE" },
    { "rank": 8, "team_code": "SVK" }
  ],
  "podium": {
    "champion": "CHN",
    "runner_up": "KOR",
    "third_place": "JPN"
  }
}
```

---

## 5. 后端方案

### 5.1 赛事详情返回模型扩展

`getEventDetail()` 不再只返回 bracket 模型，而是新增：

- `presentationMode`
- `roundRobinView`

推荐模型：

```ts
type EventPresentationMode = "knockout" | "staged_round_robin";

type TeamTie = {
  tieId: string;
  stage: string;
  stageZh: string | null;
  round: string;
  roundZh: string | null;
  teamA: { code: string; name: string; nameZh: string | null };
  teamB: { code: string; name: string; nameZh: string | null };
  scoreA: number;
  scoreB: number;
  winnerCode: string | null;
  rubbers: Array<{
    matchId: number;
    subEventTypeCode: string;
    matchScore: string | null;
    winnerSide: string | null;
  }>;
};

type StageStanding = {
  rank: number;
  teamCode: string;
  teamName: string;
  teamNameZh: string | null;
  played?: number;
  wins?: number;
  losses?: number;
  gamesFor?: number;
  gamesAgainst?: number;
  points?: number;
};

type EventRoundRobinView = {
  mode: "staged_round_robin";
  stages: Array<{
    code: string;
    name: string;
    nameZh: string | null;
    format: "group_round_robin" | "round_robin";
    groups?: Array<{
      code: string;
      nameZh: string | null;
      teams: string[];
      ties: TeamTie[];
      standings?: StageStanding[];
    }>;
    ties?: TeamTie[];
    standings?: StageStanding[];
  }>;
  finalStandings: StageStanding[];
  podium: {
    champion: StageStanding | null;
    runnerUp: StageStanding | null;
    thirdPlace: StageStanding | null;
  };
};
```

### 5.2 团体赛聚合逻辑

当前 `matches` 表存的是 rubber 级记录。赛事页需要的是团体赛级别对阵。

推荐聚合 key：

- `event_id`
- `sub_event_type_code`
- `stage`
- `round`
- `team_a_code`
- `team_b_code`

其中 `team_a_code / team_b_code` 可由 `match_side_players.player_country` 推导：

- 每侧所有成员国家代码必须一致
- 取该唯一国家代码作为团体队伍代码

团体赛比分计算：

- `scoreA = count(rubber winner is A)`
- `scoreB = count(rubber winner is B)`

这样可把多条 rubber 记录聚合为一场真实的 team tie。

### 5.3 冠军来源扩展

当前冠军来源只认 `Final`，需要扩展为：

- `final_match`
- `standings_override`

对于 `2860`：

- 不从 `Final` 推导
- 直接读取 `manual_event_overrides/2860.json > podium`

最小实现可以先不改表结构，在 `getEventDetail()` 中直接覆盖赛事页冠军展示。

---

## 6. 前端方案

### 6.1 赛事详情页模式切换

赛事详情页拆成两类视图：

- `BracketView`
- `RoundRobinView`

规则：

- `presentationMode === "knockout"` 时渲染现有 bracket
- `presentationMode === "staged_round_robin"` 时渲染循环赛流程视图

### 6.2 `RoundRobinView` 结构

展示顺序建议：

1. Podium
2. Stage 1 Groups
3. Stage 2 Round Robin
4. Final Standings

其中：

- Podium：冠军 / 亚军 / 季军
- Stage 1：四个小组卡片，展示队伍、组内对阵、可选 standings
- Stage 2：八强对阵、积分榜
- Final Standings：1 到 8 名完整排名

### 6.3 不再强制“对战图”

对于 `staged_round_robin`：

- 不展示淘汰树
- 展示“赛制流程图 + 分阶段对阵 + 最终排名”

流程表达应为：

```text
Stage 1 Groups
 -> Top 2 from each group advance
Stage 2 Round Robin
 -> Final standings determine champion
```

---

## 7. 数据库存储方案

### 7.1 最小可用方案

第一阶段不强制新增正式表：

- 继续使用 `matches` 保存 rubber
- 使用 `manual_event_overrides/*.json` 保存赛制和最终结果
- 在后端查询层聚合 `TeamTie`

优点：

- 对现有 schema 侵入最小
- 可以先解决 `2860` 的展示和冠军问题

### 7.2 后续可演进方案

如果后续同类赛事增多，再考虑新增正式派生表：

- `event_team_ties`
- `event_stage_standings`
- `event_presentation_overrides`

建议用途：

- `event_team_ties`：保存团体赛级别对阵
- `event_stage_standings`：保存阶段积分榜 / 排名
- `event_presentation_overrides`：保存数据库内的赛制覆盖配置

---

## 8. 对现有链路的影响

### 8.1 `import_matches.py`

- 保持现有职责不变
- 继续导入 rubber 级比赛

### 8.2 `import_event_draw_matches.py`

- 继续只服务 knockout 型赛事
- 不应尝试为 `staged_round_robin` 赛事构造 fake bracket

### 8.3 `import_sub_events.py`

需要扩展冠军来源：

- 有 `Final` 时沿用现有逻辑
- 无 `Final` 且存在 `manual_event_overrides` 时，允许从 override 写冠军

---

## 9. 实施顺序

建议按以下顺序落地：

1. 新增 `data/manual_event_overrides/2860.json`
2. 后端 `getEventDetail()` 增加 override 读取与 `presentationMode`
3. 在查询层从 `matches` 聚合 team ties
4. 前端赛事详情页新增 `RoundRobinView`
5. 冠军展示优先读取 override podium
6. 如同类赛事继续增加，再沉淀为正式派生表

---

## 10. 适用范围与边界

本方案适用于以下赛事：

- 冠军不由单场 `Final` 决出
- 存在多阶段循环赛 / 小组赛 / 积分榜赛制
- 赛事详情更适合展示“流程 + standings”，而非 knockout bracket

本方案暂不处理：

- 通用 tie-break 规则自动计算
- 从所有循环赛明细自动反推出最终积分榜
- 所有历史特殊赛制赛事的一次性统一回填

V1 目标是先正确承载 `event_id=2860`，并建立可复用的扩展口子。
