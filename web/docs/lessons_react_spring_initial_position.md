# 经验教训：EventScroller 中的 react-spring 定位与重置问题

涉及文件：`web/components/home/EventScroller.tsx`

这份文档记录了两个容易混淆、但根因不同的问题：

1. 首屏加载时，轮播先出现在 1 月，再动画滑到当前月
2. 打开月份放大层时，背景轮播偶发回到当前月

两者都和 `react-spring` 有关，但触发链不同，修法也不同。

## 问题一：首屏初始定位错误

### 现象

首页加载/刷新时，月份日历轮播应直接停在「当前月」（例如 `2026-04`），但实际渲染流程为：

1. 首帧出现在 1 月（`trackX = 0`）
2. 紧接着再用一段动画从 1 月滑到 4 月

视觉上是明显的回退闪烁。

### 根因

`@react-spring/web` 的 `useSpring` 在初始化时使用什么值，首帧就会先画什么值。

最初的写法是：

```tsx
const [{ trackX }, trackApi] = useSpring(() => ({
  trackX: 0,
  config: { tension: 260, friction: 32 },
}));

useEffect(() => {
  trackApi.start({ trackX: targetX });
}, [targetX]);
```

问题在于：

- `initialIndex` 依赖异步数据加载
- `carouselWidth` 依赖 `ResizeObserver` 测量
- `useSpring` 初始化时，这两个值都还没准备好

结果就是：

- spring 首帧先锚定在 `0`
- 后续即使算出了正确 `targetX`，也只能通过动画“滑过去”

这里还有一个关键事实：

> 在当时使用的 `react-spring` 版本里，`trackApi.set(...)` 和 `trackApi.start({ immediate: true })` 都不是调用后同步生效，它们内部仍然走 raf 调度。

也就是说，调用后立刻读 `trackX.get()`，读到的仍可能是旧值。

### 最终修复

采用“子组件拆分 + 懒初始化”：

```tsx
function CarouselTrack({ monthData, initialIndex, carouselWidth, onCardClick }) {
  const slideStep = ...;
  const baseTrackX = ...;

  const [{ trackX }, trackApi] = useSpring(() => ({
    trackX: baseTrackX - initialIndex * slideStep,
    config: { tension: 260, friction: 32 },
  }));

  useEffect(() => {
    if (isDragging) return;
    trackApi.start({ trackX: baseTrackX - activeIndex * slideStep });
  }, [activeIndex, baseTrackX, slideStep, trackApi, isDragging]);

  return (...);
}

function EventScroller() {
  const canShowCarousel = !loading && monthData.length > 0 && carouselWidth > 0;

  return (
    <>
      <div ref={sizerRef} />
      {canShowCarousel && (
        <CarouselTrack
          monthData={monthData}
          initialIndex={initialIndex}
          carouselWidth={carouselWidth}
          onCardClick={setExpandedMonthId}
        />
      )}
    </>
  );
}
```

核心点：

1. `CarouselTrack` 只在依赖都就绪后才挂载
2. `useSpring` 第一次初始化时就拿到正确 `trackX`
3. 后续切月才走 `trackApi.start(...)` 的平滑动画

### 这次踩过的坑

#### 坑 1：以为 `trackApi.set()` 是同步的

```tsx
useLayoutEffect(() => {
  trackApi.set({ trackX: targetX });
}, [targetX]);
```

实际不是同步，仍然晚一帧。

#### 坑 2：以为 `start({ immediate: true })` 是同步的

```tsx
trackApi.start({ trackX: targetX, immediate: true });
```

实际 `immediate` 只是“不插值”，不是“调用后当前帧立即可见”。

#### 坑 3：把希望寄托在 `useLayoutEffect`

`useLayoutEffect` 只能保证 effect 自身执行时机，控制不了 `react-spring` 内部的 raf 调度。

#### 坑 4：试图用 opacity / 显隐遮住首帧

遮挡只能掩盖现象，不能修正 spring 的真实初始位置。

#### 坑 5：忽略月份排序

`buildMonthCards` 如果不排序，`initialIndex` 本身也可能偶发算错。

修复方式：

```tsx
.sort((a, b) => a.year * 12 + a.month - (b.year * 12 + b.month));
```

### 这一类问题的一句话总结

> 想让首帧落在正确位置，唯一可靠的做法是让 `useSpring` 在首次初始化时就拿到正确初值；`set()` 与 `start({ immediate: true })` 都不能事后补救首帧。

## 问题二：modal 打开时背景轮播回到当前月

### 现象

后续又遇到一个表面相似、但根因不同的问题：

1. 手动把轮播划到其他月份，例如 6 月
2. 点击卡片放大
3. 能看到遮罩层背后的卡片又滑回当前月
4. 关闭放大后，卡片再从当前月自动滑回刚才选中的月份

这类问题：

- 不是首屏初始定位问题
- 也不是 `activeIndex` 失真

### 先排掉的错误假设

排查时先验证了这几件事：

1. 点击时 `clickedIndex === activeIndex`
2. 父组件只是在切换 `expandedMonthId`，`initialIndex` 没变
3. `CarouselTrack` 没有发生 unmount / mount

因此可以排除：

- 不是点到了“非当前卡片”
- 不是 `activeIndex` 被重置回当前月
- 不是组件 remount 导致 `useState(initialIndex)` 重新初始化

### 关键证据

曾拿到过这样一组关键数据：

```ts
initialIndex = 3
activeIndex = 5
baseTrackX = 60
slideStep = 256
currentTrackX = -708
```

代入计算：

```ts
// 当前月（initialIndex = 3）的目标位置
60 - 3 * 256 = -708

// 用户实际选中月份（activeIndex = 5）的目标位置
60 - 5 * 256 = -1220
```

这说明：

- React state 里的 `activeIndex` 还是 5
- spring 输出的 `trackX` 却已经回到了 `initialIndex = 3` 对应的位置

所以这个问题的真正定义是：

> 打开 modal 时，背景轮播的 spring 视觉层被重置了；但逻辑选中态 `activeIndex` 没丢，所以关闭 modal 后又会重新动画回选中的月份。

### 一次误修复：冻结背景轮播

中途曾尝试过：

1. 引入 `trackXRef`
2. modal 打开时冻结背景轮播同步逻辑

结果表现是：

- 打开放大时，背景先回到当前月
- 关闭放大时，再从当前月滑回刚才选中的月份

这说明“冻结”只是让关闭时更明显地补了一次动画，并没有解决“打开时为何会回退”。

结论：

> 当现象是“打开时回退，关闭时再滑回”时，冻结不是修复，只是把状态和视觉重新对齐的副作用变得更显眼。

### 真正根因

真正的问题在于：

- `expandedMonthId` 的变化会让父组件 rerender
- 轮播组件也被一起重新 render
- 在这套 `react-spring` 版本和写法组合下，这次 rerender 会让 spring 视觉输出回到初始化位置

注意：

> 这里即使没有 remount，也仍然可能出现 spring 视觉层被重置。

所以判断这类 bug，不能只看“组件有没有卸载重挂”，还必须同时看：

- `activeIndex` 是否仍正确
- `trackX` 是否偷偷回到了 `initialIndex` 对应的位置

### 最终有效修复

最终采用的是“隔离轮播，避免 modal state 变化把它卷进 rerender”：

```tsx
const CarouselTrack = React.memo(function CarouselTrack(props: CarouselTrackProps) {
  ...
});
```

目标很直接：

1. modal 的开关只更新 `expandedMonthId`
2. 不让这个局部 state 更新穿透到 `CarouselTrack`
3. 让轮播在打开/关闭放大层时保持原地不动

这个修复比“冻结 spring”更靠谱，因为它切断的是问题触发链，而不是在问题发生后补偿。

### 这一类问题的一句话总结

> 当 modal 打开导致背景轮播回到初始月份时，先别急着修拖拽状态；更常见的根因是父组件的局部 state 更新把 spring 轮播卷进了不该发生的 rerender，最有效的修复通常是把轮播从这次 rerender 里隔离出去。

## 通用排查规则

这两个问题沉淀出几条更通用的规则：

1. **react-spring 的问题不一定只发生在 mount。** 初始化错会出问题，某些 rerender 也会出问题。
2. **判断 spring 问题时，不能只看 React state。** 最少要一起看：
   - `initialIndex`
   - `activeIndex`
   - `trackX.get()`
   - `baseTrackX`
   - `slideStep`
3. **不要先相信 `set()` 和 `start({ immediate: true })` 会同步生效。** 需要首帧正确时，优先让 spring 初始化时就拿到正确值。
4. **如果某个 UI 只是覆盖层，不应该顺带扰动背景动画组件。** 更稳的做法通常是把背景组件隔离出这次 rerender，例如 `React.memo`。
5. **“冻结”“遮挡”“关闭时补动画”通常只是缓解表现。** 如果打开时已经出错，优先追查是谁触发了这次错误渲染。
6. **当假设和现象不符时，先加日志证伪。** 尤其是 spring 问题，日志比“感觉上应该是这样”可靠得多。

## 最后总结

`EventScroller` 里的两个问题虽然都表现为“月份回退”，但处理思路完全不同：

- 首屏回退：本质是 spring 初始化值错误，要靠懒初始化解决
- modal 回退：本质是局部 state 更新把背景轮播卷进 rerender，要靠隔离渲染解决

把“初始化问题”和“rerender 重置问题”分开看，诊断会快很多，修法也不会互相污染。
